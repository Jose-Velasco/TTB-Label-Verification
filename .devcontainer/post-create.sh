#!/usr/bin/env bash
# Runs once after the container is first created (or after "Rebuild Container").
# Installs all dependencies so the project is ready to work on immediately.
set -euo pipefail

echo "==> Installing backend dependencies (UV)..."
cd /workspace/backend
uv sync --dev

echo "==> Installing frontend dependencies (npm)..."
cd /workspace/frontend
npm install

echo ""
echo "✅ Dev container setup complete!"
echo "   Use the Command Palette → 'Tasks: Run Task' → 'Start: All' to launch"
echo "   the backend and frontend, or run them individually."
echo ""
echo "   Backend:  http://localhost:8000  (Swagger UI at /docs)"
echo "   Frontend: http://localhost:3000"
echo "   Access key: dev-access-key-change-me (from .env.dev)"
