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

import json
import logging
import os
import queue
import threading

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator

from . import DISCLAIMER, __version__
from .cards import card_payload
from .env import load_dotenv
from .verdict import run_live

load_dotenv()  # make `uvicorn verdict.webapp:app` turnkey from the repo .env; real env vars still win

log = logging.getLogger("verdict.webapp")

app = FastAPI(title="Verdict", version=__version__, description="A decidable evidence resolver.")

# Local, public-data, no-auth tool: permissive CORS so a separately-served UI (e.g. the Vite dev
# server on another port) can call the API without a proxy. No credentials are ever sent.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=False,
)


class ResolveRequest(BaseModel):
    claim: str
    k: int = 8

    @field_validator("claim")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) < 3:
            raise ValueError("claim is too short to resolve")
        return v

    @field_validator("k")
    @classmethod
    def _bounded_k(cls, v: int) -> int:
        return max(1, min(12, v))


# --- the plain-LLM foil (the Duel's left panel for a live claim) -------------------------------
# A deliberately confident, unsourced yes/no — the exact failure mode Verdict is built to avoid.
# It is NEVER part of the verdict path; it exists only to be contrasted with the gated result.
_FOIL_TOOL = {
    "name": "answer",
    "description": "A direct, confident yes/no answer to a clinical efficacy claim, as a general "
                   "assistant would give it without consulting sources.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {"type": "string", "enum": ["Yes", "No"]},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "text": {"type": "string", "description": "one confident sentence, no hedging, no citations"},
        },
        "required": ["answer", "confidence", "text"],
    },
}
_FOIL_SYSTEM = ("You are a general-purpose assistant answering a clinical question directly and "
                "confidently, the way a chat model does when asked offhand — no tools, no sources, "
                "no hedging. Give a single decisive sentence.")


def plain_llm_baseline(claim: str) -> dict | None:
    """One confident, unsourced Claude answer — the Duel foil. Non-fatal: returns None on any
    error so a failed foil never breaks resolution (the UI falls back to a generic answer)."""
    try:
        from .parse import call_tool
        d = call_tool(_FOIL_SYSTEM, f"Claim: {claim}", _FOIL_TOOL, max_tokens=300)
        return {"answer": d.get("answer", "Yes"), "confidence": d.get("confidence", "high"),
                "text": d.get("text", "")}
    except Exception:  # noqa: BLE001 — the foil is decorative; never let it sink the request
        log.warning("plain_llm_baseline failed; falling back to no baseline", exc_info=True)
        return None


def _resolve_card(claim: str, k: int) -> dict:
    card = run_live(claim, k=k)
    return card_payload(card, id="LIVE", baseline=plain_llm_baseline(claim))


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "verdict", "version": __version__, "disclaimer": DISCLAIMER}


@app.post("/api/resolve")
def resolve(req: ResolveRequest) -> dict:
    try:
        return _resolve_card(req.claim, req.k)
    except Exception as e:  # noqa: BLE001
        log.exception("live resolution failed")
        # Generic detail only — never surface the exception text (it can carry keys / internals).
        raise HTTPException(status_code=502, detail="live resolution failed — see server logs") from e


def _sse_frame(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream(claim: str, k: int):
    """Run run_live on a worker thread, relaying its progress events to the client as SSE, then the
    final card. run_live is blocking, so a thread + queue lets us stream without awaiting it whole."""
    q: queue.Queue = queue.Queue()

    def worker() -> None:
        try:
            card = run_live(claim, k=k, on_event=lambda ev: q.put(("progress", ev)))
            q.put(("card", card_payload(card, id="LIVE", baseline=plain_llm_baseline(claim))))
        except Exception:  # noqa: BLE001
            log.exception("live resolution failed (stream)")
            # Named "failed", not "error": EventSource reserves the "error" event for transport
            # failures, so a server-sent `event: error` would be swallowed by the client's onerror.
            q.put(("failed", {"message": "live resolution failed — see server logs"}))
        finally:
            q.put(("done", None))

    threading.Thread(target=worker, daemon=True).start()
    while True:
        kind, payload = q.get()
        if kind == "done":
            break
        yield _sse_frame(kind, payload)


@app.get("/api/resolve/stream")
def resolve_stream(claim: str, k: int = 8):
    claim = (claim or "").strip()
    if len(claim) < 3:
        raise HTTPException(status_code=422, detail="claim is too short to resolve")
    k = max(1, min(12, k))
    return StreamingResponse(_stream(claim, k), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- serve the built demo UI (single-binary demo) ----------------------------------------------
# Registered LAST so the /api/* routes above always take precedence over the catch-all mount.
_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")
