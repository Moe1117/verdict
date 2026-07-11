# Backend for the Methods Verifier live "Verify" lane (POST /api/repro) — API only. The frontend is
# deployed separately as a static build (see DEPLOY-BACKEND.md).
#
# Required at runtime:  ANTHROPIC_API_KEY           (paid Claude calls — set on the host, NEVER baked in)
# Recommended:          VERDICT_CORS_ORIGINS=<your deployed frontend origin, comma-separated>
#                       VERDICT_DAILY_CAP=<n>       (daily paid-call budget; default 300, 0 = unlimited)
FROM python:3.12-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir ".[web]"

ENV PORT=8010 \
    VERDICT_DAILY_CAP=300
EXPOSE 8010

# Hosts that inject $PORT (Render/Railway/Fly/Cloud Run) are honoured; defaults to 8010 locally.
CMD ["sh", "-c", "python -m uvicorn verdict.webapp:app --host 0.0.0.0 --port ${PORT}"]
