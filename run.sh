#!/usr/bin/env bash
# Dev convenience: build the frontend once and serve everything from FastAPI on :8000
set -e
cd "$(dirname "$0")"
[ -f .env ] || cp .env.example .env
pip install -q -r backend/requirements.txt
(cd frontend && npm install --silent && npm run build --silent)
cd backend && exec python -m uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
