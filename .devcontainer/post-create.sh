#!/usr/bin/env bash
# Runs once after the container is first created (or after "Rebuild Container").
# Installs all dependencies so the project is ready to work on immediately.
set -euo pipefail

echo "==> Installing backend dependencies (UV)..."
sudo chown -R vscode:vscode /home/vscode/.cache/uv
cd /workspace/backend
# This project's dev deps are declared as the "dev" extra (PEP 621
# optional-dependencies), not a PEP 735 dependency-group — `--dev` toggles the
# latter and is a silent no-op here, leaving pytest etc. uninstalled.
uv sync --extra dev

echo ""
echo "✅ Dev container setup complete!"
echo "   Use the Command Palette → 'Tasks: Run Task' → 'Start: All' to launch"
echo "   the backend and frontend, or run them individually."
echo ""
echo "   Backend:  http://localhost:8000  (Swagger UI at /docs)"
echo "   Frontend: http://localhost:4200"
echo "   Access key: dev-access-key-change-me (from .env.dev)"
