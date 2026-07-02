#!/usr/bin/env bash
# Start the DronAI server manually (development / debugging).
# For production use the systemd service instead: sudo systemctl start dronai
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SERVER_DIR"

if [ -x ".venv/bin/uvicorn" ]; then
    exec .venv/bin/uvicorn main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
else
    exec python3 -m uvicorn main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
fi
