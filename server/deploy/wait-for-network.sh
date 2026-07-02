#!/usr/bin/env bash
# Boot-time network verification (systemd ExecStartPre).
#
# Waits up to TIMEOUT seconds for the Wi-Fi connection configured by
# install.sh to come up and verifies connectivity (IP address / gateway
# reachability). Logs the outcome to the journal.
#
# Always exits 0: the drone server must still start when the router is off —
# the Pixhawk link, camera, and mission automation do not need a network,
# and the website becomes reachable as soon as Wi-Fi appears.
TIMEOUT="${NETWORK_WAIT_TIMEOUT:-60}"

echo "Verifying network connectivity (timeout ${TIMEOUT}s)…"
for ((i = 0; i < TIMEOUT; i++)); do
    # Connected per NetworkManager? (full = internet, limited = LAN only)
    if command -v nmcli > /dev/null 2>&1; then
        state="$(nmcli networking connectivity check 2>/dev/null || true)"
        if [ "$state" = "full" ] || [ "$state" = "limited" ] || [ "$state" = "portal" ]; then
            ip_addr="$(hostname -I 2>/dev/null | awk '{print $1}')"
            echo "Network up (connectivity=$state, ip=${ip_addr:-unknown})."
            exit 0
        fi
    fi
    # Fallback check: any non-loopback IPv4 address present?
    if hostname -I 2>/dev/null | grep -q '[0-9]'; then
        echo "Network up (ip=$(hostname -I | awk '{print $1}'))."
        exit 0
    fi
    sleep 1
done

echo "WARNING: no network after ${TIMEOUT}s — starting anyway (offline mode)."
exit 0
