#!/usr/bin/env bash
# Generates (or refreshes) a self-signed TLS cert/key for DronAI so the
# website can be served over HTTPS — required for the browser Geolocation
# API ("My Location"), which every browser blocks on a plain-HTTP LAN
# address like http://<pi-ip>:8000.
#
# Idempotent and safe to run on every boot (called from dronai.service's
# ExecStartPre, after wait-for-network.sh): if a cert already exists and
# already covers the Pi's current LAN IP, it's left alone. DHCP can hand out
# a different IP after a reboot, so the cert is regenerated automatically
# when that happens rather than going stale.
set -euo pipefail

SERVER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="$SERVER_DIR/deploy/certs"
CERT_FILE="$CERT_DIR/dronai.crt"
KEY_FILE="$CERT_DIR/dronai.key"

CURRENT_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [ -z "$CURRENT_IP" ]; then
    CURRENT_IP="$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i=="src") print $(i+1)}')"
fi
if [ -z "$CURRENT_IP" ]; then
    echo "generate-cert.sh: could not determine a LAN IP — skipping (HTTPS will stay disabled)."
    exit 0
fi

if [ -f "$CERT_FILE" ] && openssl x509 -in "$CERT_FILE" -noout -text 2>/dev/null | grep -q "$CURRENT_IP"; then
    echo "generate-cert.sh: existing cert already covers $CURRENT_IP — nothing to do."
    exit 0
fi

echo "generate-cert.sh: generating self-signed cert for $CURRENT_IP (and localhost)."
mkdir -p "$CERT_DIR"
openssl req -x509 -newkey rsa:2048 -sha256 -days 3650 -nodes \
    -keyout "$KEY_FILE" -out "$CERT_FILE" \
    -subj "/CN=dronai" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1,IP:${CURRENT_IP}"
chmod 600 "$KEY_FILE"
echo "generate-cert.sh: wrote $CERT_FILE and $KEY_FILE."
