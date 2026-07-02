#!/usr/bin/env bash
# DronAI unified server — Raspberry Pi 5 installation script.
# Run on the Pi from the repo root:  bash server/deploy/install.sh
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_FILE="$SERVER_DIR/deploy/dronai.service"
RUN_USER="${SUDO_USER:-$(whoami)}"

echo "==> Installing DronAI server from $SERVER_DIR (user: $RUN_USER)"

# ── System packages ────────────────────────────────────────────────────────────
echo "==> Installing system packages"
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev libatlas-base-dev \
    libavdevice-dev libavfilter-dev libopus-dev libvpx-dev libsrtp2-dev \
    v4l-utils

# ── Serial + video permissions ─────────────────────────────────────────────────
echo "==> Adding $RUN_USER to dialout (Pixhawk serial) and video (camera) groups"
sudo usermod -aG dialout,video "$RUN_USER"

# ── Python virtual environment ─────────────────────────────────────────────────
echo "==> Creating virtualenv and installing Python dependencies"
cd "$SERVER_DIR"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# ── systemd service ────────────────────────────────────────────────────────────
echo "==> Installing systemd service"
# Rewrite the unit's paths/user to match this checkout before installing.
sed -e "s|/home/pi/DronAi/server|$SERVER_DIR|g" \
    -e "s|^User=pi$|User=$RUN_USER|" \
    -e "s|^Group=pi$|Group=$RUN_USER|" \
    "$SERVICE_FILE" | sudo tee /etc/systemd/system/dronai.service > /dev/null

sudo systemctl daemon-reload
sudo systemctl enable dronai.service

echo ""
echo "Installation complete."
echo "  Start now:    sudo systemctl start dronai"
echo "  Check status: sudo systemctl status dronai"
echo "  Follow logs:  journalctl -u dronai -f"
echo ""
echo "NOTE: if $RUN_USER was newly added to dialout/video, log out and back in"
echo "(or reboot) before running the server manually."
