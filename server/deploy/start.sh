#!/usr/bin/env bash
# Start the DronAI server. Used by the systemd unit (ExecStart) and for
# manual development runs. Host/port come from the central configuration
# (config.py, overridable via server/.env or environment) — nothing is
# hardcoded here.
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SERVER_DIR"

if [ -x ".venv/bin/python" ]; then
    PY=".venv/bin/python"
else
    PY="python3"
fi

HOST="$($PY -c "from config import settings; print(settings.HOST)")"
PORT="$($PY -c "from config import settings; print(settings.PORT)")"

echo "Starting DronAI on ${HOST}:${PORT}"
exec "$PY" -m uvicorn main:app --host "$HOST" --port "$PORT"
