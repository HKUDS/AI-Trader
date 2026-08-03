# AI-Trader Server

The FastAPI backend, the standalone background worker, and the Vite/React
frontend. Same license as the rest of the repository — see the
[root README](../README.md#license).

## Contents

- `server/` — FastAPI app (`main.py`), background worker (`worker.py`), routes,
  services, and the SQLite/Postgres data layer
- `frontend/` — Vite/React single-page app
- `requirements.txt` — Python dependencies for both `server` processes

## Deployment

See the [root README](../README.md) for one-click deployment on Render. The
Blueprint is at [`render.yaml`](../render.yaml).
