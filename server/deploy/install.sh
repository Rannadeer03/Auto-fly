#!/usr/bin/env bash
# DronAI drone computer — Raspberry Pi 5 installation script.
#
# Makes the Pi fully autonomous: Wi-Fi auto-connect, UART for the Pixhawk,
# Python environment, and a systemd service that starts DronAI on boot.
# After this script + one reboot, no manual commands are ever needed.
#
# Run on the Pi from the repo root:  bash server/deploy/install.sh
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_FILE="$SERVER_DIR/deploy/dronai.service"
RUN_USER="${SUDO_USER:-$(whoami)}"

echo "==> Installing DronAI from $SERVER_DIR (user: $RUN_USER)"

# ── System packages ────────────────────────────────────────────────────────────
echo "==> Installing system packages"
sudo apt-get update
sudo apt-get install -y python3-venv python3-dev v4l-utils network-manager

# ── Wi-Fi auto-connect (values come from server/config.py) ─────────────────────
WIFI_SSID="$(python3 -c "import sys; sys.path.insert(0,'$SERVER_DIR'); from config import settings; print(settings.WIFI_SSID)")"
WIFI_PASSWORD="$(python3 -c "import sys; sys.path.insert(0,'$SERVER_DIR'); from config import settings; print(settings.WIFI_PASSWORD)")"

echo "==> Configuring Wi-Fi auto-connect to '$WIFI_SSID'"
if nmcli -t -f NAME connection show | grep -Fxq "$WIFI_SSID"; then
    echo "    Connection profile already exists — updating password."
    sudo nmcli connection modify "$WIFI_SSID" wifi-sec.psk "$WIFI_PASSWORD" \
        connection.autoconnect yes connection.autoconnect-priority 10
else
    sudo nmcli connection add type wifi ifname "*" con-name "$WIFI_SSID" \
        ssid "$WIFI_SSID" \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$WIFI_PASSWORD" \
        connection.autoconnect yes connection.autoconnect-priority 10
fi
# Make boot wait for the network so the service starts with Wi-Fi up.
sudo systemctl enable NetworkManager-wait-online.service

# ── UART for the Pixhawk (/dev/serial0 on GPIO 14/15) ──────────────────────────
echo "==> Enabling UART for Pixhawk communication"
BOOT_CONFIG="/boot/firmware/config.txt"
[ -f "$BOOT_CONFIG" ] || BOOT_CONFIG="/boot/config.txt"
if ! grep -q "^enable_uart=1" "$BOOT_CONFIG"; then
    echo "enable_uart=1" | sudo tee -a "$BOOT_CONFIG" > /dev/null
    echo "    enable_uart=1 added to $BOOT_CONFIG (reboot required)."
fi
# Free the UART from the serial login console if it is attached.
CMDLINE="/boot/firmware/cmdline.txt"
[ -f "$CMDLINE" ] || CMDLINE="/boot/cmdline.txt"
if grep -q "console=serial0" "$CMDLINE"; then
    sudo sed -i 's/console=serial0,[0-9]* //' "$CMDLINE"
    echo "    Serial console removed from $CMDLINE (reboot required)."
fi
sudo systemctl disable --now serial-getty@ttyAMA0.service 2>/dev/null || true
sudo systemctl disable --now serial-getty@ttyS0.service 2>/dev/null || true

# ── Serial + video permissions ─────────────────────────────────────────────────
echo "==> Adding $RUN_USER to dialout (UART) and video (camera) groups"
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
echo "Installation complete. Reboot to activate everything:"
echo "    sudo reboot"
echo ""
echo "After reboot the Pi will automatically:"
echo "  1. Connect to Wi-Fi '$WIFI_SSID'"
echo "  2. Start DronAI (systemd service 'dronai')"
echo "  3. Connect to the Pixhawk on /dev/serial0 (UART)"
echo "  4. Initialise the camera and mapping system"
echo "  5. Serve the website on http://<pi-ip>:8000"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status dronai     # service status"
echo "  journalctl -u dronai -f          # live logs"
