# Deploy — make the live "Verify" lane judge-drivable

The Methods Verifier has two pieces:

- **Frontend** (static build, no secrets) — the UI + the frozen demo card + benchmark panel. Deploys
  to any static host; works with **no backend** (shows saved examples).
- **Backend** (`verdict/webapp.py`, `POST /api/repro`) — makes paid Claude calls. This is what powers
  the live **"Verify"** button so a judge can paste their own Methods and watch it resolve.

Deploying the frontend alone gets you a working demo of the frozen examples. Deploying the backend too
is what makes the demo **judge-drivable** — the difference a judge feels between "a reel" and "software
I can try."

Everything in this repo is already prepared for both. The only steps that need **you** are the ones
that require your account + your API key (I can't log into your host or handle your key).

---

## 1. Backend — container (≈5 min)

A `Dockerfile` + `.dockerignore` are in the repo root. The image is API-only (it does not serve the
UI). Any container host works; **Render** is the least-friction for a Dockerfile:

1. Push this branch to GitHub (public or private).
2. Render → **New → Web Service** → connect the repo → it auto-detects the `Dockerfile`.
3. Set **environment variables**:
   - `ANTHROPIC_API_KEY` = your key **(required; set it here, never commit it)**
   - `VERDICT_CORS_ORIGINS` = your frontend origin, e.g. `https://methods-verifier.netlify.app`
   - `VERDICT_DAILY_CAP` = `300` (default; the daily paid-call budget — see §3)
4. Deploy. Confirm health: `curl https://<your-backend>.onrender.com/api/health` → `{"status":"ok",…}`.

Alternatives (same image, same env vars): **Fly.io** (`fly launch` → `fly secrets set ANTHROPIC_API_KEY=…`),
**Railway** (New → Deploy from repo → Variables), **Cloud Run** (`gcloud run deploy --source .`). All
honour the injected `$PORT`.

> ⚠️ Do **not** deploy to Vercel/Netlify *functions* for the backend — the SSE/threaded sibling
> endpoints don't fit serverless, and the register load wants a warm process. A container is the fit.

## 2. Frontend — static (≈3 min)

`netlify.toml` is already present.

1. `cd web && npm install && npm run build`  → outputs `web/dist`.
2. Deploy `web/dist` to Netlify (drag-and-drop, or connect the repo with build command `npm run build`
   and publish dir `web/dist`).
3. Set the frontend build env var so "Verify" targets your backend:
   - `VITE_API_BASE` = `https://<your-backend>.onrender.com`
   (Netlify → Site settings → Environment → add it, then redeploy. Local dev needs nothing — it proxies
   to `:8010`.)
4. Open the site: the frozen card + benchmark render immediately; **"Verify"** now hits your live
   backend end-to-end.

Then fill the two links in `README.md` / `SUBMISSION.md` (`_(link)_` → the Netlify URL) and the demo
video link once recorded.

## 3. Cost & abuse — before you make it public

`POST /api/repro` is **unauthenticated and paid** (extraction + one knockout-reasoning call per
antibody). Two guards ship in the code:

- **Concurrency cap** (`VERDICT_MAX_CONCURRENT`, default 4) — bounds *simultaneous* spend.
- **Daily cap** (`VERDICT_DAILY_CAP`, default 300) — bounds *total* paid calls per UTC day; returns
  `429` past the limit. It's a soft in-process counter (resets on restart), so **also set a hard
  monthly budget alert on the Anthropic Console** as the real ceiling.

For a short judging window, `VERDICT_DAILY_CAP=300` is plenty for judges and cheap to run. Raise or
lower it via the env var; `0` = unlimited (not recommended for a public URL).

---

## What I could not do for you (and why)

- **Create/authenticate to the host** and **set `ANTHROPIC_API_KEY` on it** — that's your account and
  your secret; I don't have either and can't enter credentials on your behalf.
- **Click the final "deploy"** — it publishes a public, paid endpoint; that's yours to trigger.

Everything else — the container config, the spend guard, the frontend API-base wiring, and this runbook
— is done. The above is ~10 minutes end to end.
