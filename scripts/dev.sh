#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(node -p 'process.versions.node.split(".")[0]')" != "24" ]]; then
  echo 'Node 24 is required. Run nvm use (or install Node 24 LTS).'
  exit 1
fi
docker compose up -d db --wait
uv run --directory apps/backend alembic upgrade head
uv run --directory apps/backend uvicorn app.main:app --host 127.0.0.1 --port 8000 &
warehouse_backend_pid=$!
trap 'kill "$warehouse_backend_pid" 2>/dev/null || true' EXIT INT TERM
npm --prefix apps/frontend run dev
