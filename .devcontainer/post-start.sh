#!/usr/bin/env bash
set -euo pipefail

echo "==> Starting backend server..."

cd /workspace/backend

# Avoid starting duplicate uvicorn processes
if pgrep -f "uvicorn app.main:app.*--port 8000" > /dev/null; then
  echo "Backend already running on port 8000."
  exit 0
fi

nohup uv run uvicorn app.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload \
  > /tmp/backend.log 2>&1 &

echo "Backend started."
echo "Logs: /tmp/backend.log"
echo "URL:  http://localhost:8000"
echo "Docs: http://localhost:8000/docs"
