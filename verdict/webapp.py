"""Live API for Verdict — wraps the deterministic resolver in HTTP so a pasted clinical claim can
be resolved end-to-end, and serves the built demo UI as static files.

  POST /api/resolve         {claim, k?}  -> a web Card (id="LIVE"), resolved end-to-end (~40s)
  GET  /api/resolve/stream  ?claim&k     -> Server-Sent Events: the pipeline as it runs, then the card
  GET  /api/health                       -> liveness

The verdict is still a pure function of the extracted evidence (no LLM in the verdict path); the
API only wraps run_live. The frozen deck (web/public/cards.json) is unaffected and remains the
demo's guaranteed fallback — the live lane is additive.

Run:  PYTHONPATH=. .venv/bin/python -m uvicorn verdict.webapp:app --port 8000
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import queue
import threading
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from . import DISCLAIMER, __version__
from .baseline import plain_llm_baseline
from .cards import card_payload
from .env import load_dotenv
from .trialmatch import card_to_dict, review
from .investigate import Investigation, investigate_antibody, investigate_cell_line
from .repro import report_to_dict
from .repro import review as repro_review
from .verdict import run_live

load_dotenv()  # make `uvicorn verdict.webapp:app` turnkey from the repo .env; real env vars still win

log = logging.getLogger("verdict.webapp")

# A real clinical claim is a sentence; anything longer is embedded verbatim into paid Claude
# prompts, so cap it at the validation boundary. The endpoints are unauthenticated, so a
# concurrency cap bounds how many paid resolutions can run at once — excess requests get 429
# rather than fanning out into unbounded Claude spend.
MAX_CLAIM_LEN = int(os.getenv("VERDICT_MAX_CLAIM_LEN", "600"))
# A clinical note is a paragraph, not a sentence — much longer than a claim — but still bounded
# because it too is embedded verbatim into paid Claude prompts (profile extraction + per-criterion
# matching across several candidate trials). Same rationale as MAX_CLAIM_LEN, larger ceiling.
MAX_NOTE_LEN = int(os.getenv("VERDICT_MAX_NOTE_LEN", "4000"))
MAX_METHODS_LEN = int(os.getenv("VERDICT_MAX_METHODS_LEN", "8000"))
_MAX_CONCURRENT = int(os.getenv("VERDICT_MAX_CONCURRENT", "4"))
_slots = threading.BoundedSemaphore(_MAX_CONCURRENT)

# A public, unauthenticated demo endpoint spends paid Claude budget per call. The concurrency cap
# bounds SIMULTANEOUS spend; this daily cap bounds TOTAL spend per UTC day across the paid endpoints
# (0 = unlimited). It is a soft in-process cap (resets on process restart) — for a hard ceiling, also
# set a budget alert on the Anthropic console. Sized for a judge-facing demo; tune via VERDICT_DAILY_CAP.
_DAILY_CAP = int(os.getenv("VERDICT_DAILY_CAP", "300"))
_day_lock = threading.Lock()
_day_state = {"day": None, "count": 0}


def _daily_gate() -> None:
    if _DAILY_CAP <= 0:
        return
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    with _day_lock:
        if _day_state["day"] != today:
            _day_state["day"], _day_state["count"] = today, 0
        if _day_state["count"] >= _DAILY_CAP:
            raise HTTPException(status_code=429, detail="daily demo limit reached — try again tomorrow")
        _day_state["count"] += 1

# Scoped CORS: only the local dev UI origins may call the API cross-origin (the primary dev flow
# goes same-origin through the Vite proxy anyway). A wildcard would let any web page drive spend.
_CORS_ORIGINS = [o for o in os.getenv(
    "VERDICT_CORS_ORIGINS",
    "http://localhost:5175,http://127.0.0.1:5175,http://localhost:4173,http://localhost:8010",
).split(",") if o.strip()]

app = FastAPI(title="Verdict", version=__version__,
              description="Decidable verification for biomedical work — Methods Verifier (POST /api/repro), "
                          "trial-eligibility reviewer (/api/match), evidence resolver (/api/resolve).")
app.add_middleware(
    CORSMiddleware, allow_origins=_CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"],
    allow_credentials=False,
)


class ResolveRequest(BaseModel):
    claim: str
    k: int = 8

    @field_validator("claim")
    @classmethod
    def _bounded_claim(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 3:
            raise ValueError("claim is too short to resolve")
        if len(v) > MAX_CLAIM_LEN:
            raise ValueError(f"claim is too long (max {MAX_CLAIM_LEN} chars)")
        return v

    @field_validator("k")
    @classmethod
    def _bounded_k(cls, v: int) -> int:
        return max(1, min(12, v))


class MatchRequest(BaseModel):
    note: str
    condition: str | None = None

    @field_validator("note")
    @classmethod
    def _bounded_note(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 10:
            raise ValueError("note is too short to review")
        if len(v) > MAX_NOTE_LEN:
            raise ValueError(f"note is too long (max {MAX_NOTE_LEN} chars)")
        return v

    @field_validator("condition")
    @classmethod
    def _clean_condition(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


def _resolve_card(claim: str, k: int) -> dict:
    card = run_live(claim, k=k)
    return card_payload(card, id="LIVE", baseline=plain_llm_baseline(claim))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "verdict", "version": __version__, "disclaimer": DISCLAIMER}


@app.post("/api/resolve")
def resolve(req: ResolveRequest) -> dict:
    if not _slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="server is busy — too many concurrent resolutions")
    try:
        return _resolve_card(req.claim, req.k)
    except Exception as e:  # noqa: BLE001
        log.exception("live resolution failed")
        # Generic detail only — never surface the exception text (it can carry keys / internals).
        raise HTTPException(status_code=502, detail="live resolution failed — see server logs") from e
    finally:
        _slots.release()


@app.post("/api/match")
def api_match(req: MatchRequest) -> dict:
    # review() fans out into several paid Claude calls (profile extraction + per-criterion matching
    # over multiple candidate trials), so it takes a concurrency slot exactly like /api/resolve.
    if not _slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="server is busy — too many concurrent reviews")
    try:
        cards = review(req.note, condition=req.condition)
        return {"note": req.note, "cards": [card_to_dict(c) for c in cards]}
    except Exception as e:  # noqa: BLE001
        log.exception("trial-eligibility review failed")
        # Generic detail only — never surface the exception text (it can carry keys / internals).
        raise HTTPException(status_code=502, detail="trial-eligibility review failed — see server logs") from e
    finally:
        _slots.release()


class ReproRequest(BaseModel):
    methods: str

    @field_validator("methods")
    @classmethod
    def _bounded_methods(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 20:
            raise ValueError("methods text is too short to review")
        if len(v) > MAX_METHODS_LEN:
            raise ValueError(f"methods text is too long (max {MAX_METHODS_LEN} chars)")
        return v


@app.post("/api/repro")
def api_repro(req: ReproRequest) -> dict:
    # review() makes paid Claude calls (extraction + one knockout-reasoning call per antibody) plus
    # deterministic gate lookups, so it takes a daily-budget slot AND a concurrency slot.
    _daily_gate()
    if not _slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="server is busy — too many concurrent reviews")
    try:
        return {"methods": req.methods, "report": report_to_dict(repro_review(req.methods))}
    except Exception as e:  # noqa: BLE001
        log.exception("repro review failed")
        raise HTTPException(status_code=502, detail="reproducibility review failed — see server logs") from e
    finally:
        _slots.release()


class InvestigateRequest(BaseModel):
    kind: str
    name: str
    target: str | None = None
    catalog: str | None = None
    rrid: str | None = None
    iclac_id: str | None = None
    cvcl: str | None = None

    @field_validator("name")
    @classmethod
    def _bounded_name(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("name is required")
        return v[:200]


@app.post("/api/investigate")
def api_investigate(req: InvestigateRequest) -> dict:
    # The agentic investigator makes several paid Claude calls + live API lookups, so it takes a
    # daily-budget slot AND a concurrency slot like the other paid endpoints.
    _daily_gate()
    if not _slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="server is busy — too many concurrent investigations")
    try:
        if req.kind == "cell_line":
            inv = investigate_cell_line(name=req.name, iclac_id=req.iclac_id or "", cvcl=req.cvcl or "")
        else:
            inv = investigate_antibody(name=req.name, target=req.target or "", catalog=req.catalog or "",
                                       rrid=req.rrid or "")
    except Exception:  # noqa: BLE001 — degrade gracefully, never 502
        log.exception("investigation failed")
        inv = Investigation(kind=req.kind, verdict="INCONCLUSIVE",
                            reasoning="investigation failed", steps=["investigation failed"])
    finally:
        _slots.release()
    return {"investigation": asdict(inv)}


def _sse_frame(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/api/resolve/stream")
async def resolve_stream(request: Request, claim: str, k: int = 8):
    claim = (claim or "").strip()
    if len(claim) < 3:
        raise HTTPException(status_code=422, detail="claim is too short to resolve")
    if len(claim) > MAX_CLAIM_LEN:
        raise HTTPException(status_code=422, detail=f"claim is too long (max {MAX_CLAIM_LEN} chars)")
    k = max(1, min(12, k))
    if not _slots.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="server is busy — too many concurrent resolutions")

    # run_live is blocking (~40s), so it runs on a worker thread and relays progress + the final
    # card through a queue. The worker owns the slot: whatever happens, it releases it in finally.
    q: queue.Queue = queue.Queue()
    stop = threading.Event()

    def worker() -> None:
        try:
            card = run_live(claim, k=k, on_event=lambda ev: q.put(("progress", ev)),
                            should_abort=stop.is_set)
            if not stop.is_set():
                q.put(("card", card_payload(card, id="LIVE", baseline=plain_llm_baseline(claim))))
        except Exception:  # noqa: BLE001
            log.exception("live resolution failed (stream)")
            # Named "failed", not "error": EventSource reserves the "error" event for transport
            # failures, so a server-sent `event: error` would be swallowed by the client's onerror.
            q.put(("failed", {"message": "live resolution failed — see server logs"}))
        finally:
            q.put(("done", None))
            _slots.release()

    threading.Thread(target=worker, daemon=True).start()

    async def gen():
        # Poll the worker queue AND the client connection: if the client disconnects, signal the
        # worker to abort (stop paying for a resolution no one is reading) instead of running on.
        try:
            while True:
                if await request.is_disconnected():
                    stop.set()
                    break
                try:
                    kind, payload = q.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.1)
                    continue
                if kind == "done":
                    break
                yield _sse_frame(kind, payload)
        finally:
            stop.set()  # wind the worker down even if the generator is closed early

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- serve the built demo UI (single-binary demo) ----------------------------------------------
# Registered LAST so the /api/* routes above always take precedence over the catch-all mount.
_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")
