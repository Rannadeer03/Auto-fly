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
SSL_CERTFILE="$($PY -c "from config import settings; print(settings.SSL_CERTFILE)")"
SSL_KEYFILE="$($PY -c "from config import settings; print(settings.SSL_KEYFILE)")"

# Single worker only: drone_state/camera_service/mission_runner are process-
# wide singletons — a second worker process would hold its own disconnected
# copies and silently break MAVLink/camera coordination. --no-access-log
# cuts a per-request log line (disk I/O) for every 1 Hz telemetry poll,
# which adds up on an SD card over a long autonomous mission; the app's own
# logger (services/log_service.py, surfaced at GET /logs) already captures
# everything operationally meaningful.
UVICORN_ARGS=(main:app --host "$HOST" --port "$PORT" --no-access-log)

# Serve HTTPS whenever deploy/generate-cert.sh has produced a cert/key pair
# (dronai.service runs it on every boot) — the browser Geolocation API
# ("My Location") is only available in a secure context (HTTPS or
# localhost), so a plain-HTTP LAN address blocks it outright. Falls back to
# plain HTTP when no cert exists (e.g. local dev), where a self-signed cert
# buys nothing since localhost is already secure.
if [ -f "$SSL_CERTFILE" ] && [ -f "$SSL_KEYFILE" ]; then
    echo "Starting DronAI on https://${HOST}:${PORT} (self-signed cert)"
    UVICORN_ARGS+=(--ssl-certfile "$SSL_CERTFILE" --ssl-keyfile "$SSL_KEYFILE")
else
    echo "Starting DronAI on http://${HOST}:${PORT} (no cert found — run deploy/generate-cert.sh for HTTPS)"
fi

exec "$PY" -m uvicorn "${UVICORN_ARGS[@]}"
