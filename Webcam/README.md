# DronAI WebRTC Subsystem

Production-quality WebRTC video streaming for the DronAI drone platform.
Runs entirely on a Raspberry Pi 5 — no cloud, no internet dependency. The
browser connects directly to the Pi over the local network.

See `backend/` for the implementation; architectural rationale for every
major decision is documented as docstrings/comments at the top of each
module (`config.py`, `services/camera.py`, `services/webrtc_manager.py`,
`routers/webrtc.py`, `app.py`, `utils/logger.py`).

## Directory Structure

```
Webcam/
├── README.md
├── requirements.txt
├── .gitignore
├── deploy/
│   └── backend.service          # systemd unit for auto-start on boot
└── backend/
    ├── app.py                  # FastAPI app, lifespan startup/shutdown
    ├── config.py                # CameraConfig / AppConfig (env-overridable)
    ├── routers/
    │   └── webrtc.py            # GET /, /health, /api/status, POST /offer
    ├── services/
    │   ├── camera.py            # Threaded Camera capture service
    │   └── webrtc_manager.py    # CameraVideoStreamTrack, MediaRelay, peer lifecycle
    ├── static/
    │   ├── index.html
    │   └── client.js             # auto connect/reconnect + live stats
    └── utils/
        └── logger.py             # console + rotating file logging
```

## Installation

### On a development machine (macOS/Linux, USB webcam)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### On the Raspberry Pi 5

`aiortc` and `av` (PyAV) wrap native libraries (libavcodec, libsrtp, openssl)
that are slow to compile from source on a Pi. Install system dependencies
first and let `piwheels` (Raspberry Pi OS's default pip index) provide
prebuilt ARM wheels instead of compiling:

```bash
sudo apt update
sudo apt install -y \
    python3-venv python3-dev pkg-config \
    libavdevice-dev libavfilter-dev libavformat-dev libavcodec-dev \
    libswscale-dev libswresample-dev libavutil-dev \
    libopus-dev libvpx-dev libsrtp2-dev \
    libatlas-base-dev ffmpeg

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

If a wheel still isn't available for your Pi OS/Python version, `pip` will
fall back to building from source using the headers installed above — slow
(10-20 minutes) but it will succeed.

## Running

```bash
source .venv/bin/activate
uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Configuration is via environment variables (all optional — see
`backend/config.py` for defaults):

| Variable               | Default        | Purpose                         |
|------------------------|----------------|----------------------------------|
| `DRONAI_CAMERA_DEVICE` | `/dev/video0`  | Capture device path or index     |
| `DRONAI_CAMERA_WIDTH`  | `1280`         | Capture width                    |
| `DRONAI_CAMERA_HEIGHT` | `720`          | Capture height                   |
| `DRONAI_CAMERA_FPS`    | `30`           | Target capture/stream fps        |
| `DRONAI_CAMERA_MJPEG`  | `true`         | Request MJPEG from the driver    |
| `DRONAI_HOST`          | `0.0.0.0`      | Bind host                        |
| `DRONAI_PORT`          | `8000`         | Bind port                        |
| `DRONAI_LOG_DIR`       | `./logs`       | Rotating log file location       |

## Automatic Startup on Boot (systemd)

The goal: apply power to the Pi and the backend (with the camera already
initialized) is up with no monitor, keyboard, SSH, or manual command. This
does not change any backend code — `backend/app.py`'s `lifespan` already
starts the camera unconditionally at process startup (it does not wait for
a browser to connect), and already releases the camera and closes peer
connections on shutdown. The only missing piece was getting that process
launched automatically by the OS, which is what `deploy/backend.service`
(a systemd unit) does.

### 1. Edit the placeholders in `deploy/backend.service`

The unit assumes the repo is cloned to `/home/pi/Webcam-pi` and runs as
user `pi`. If your Pi uses a different username or clone path, edit these
three lines accordingly before installing:

```ini
User=pi
WorkingDirectory=/home/pi/Webcam-pi
Environment=PATH=/home/pi/Webcam-pi/.venv/bin
ExecStart=/home/pi/Webcam-pi/.venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

The venv at `.venv` must already exist on the Pi with dependencies
installed (see **Installation → On the Raspberry Pi 5** above) — the
service does not create it.

### 2. Install the service

```bash
sudo cp deploy/backend.service /etc/systemd/system/backend.service
sudo systemctl daemon-reload
sudo systemctl enable backend.service
sudo systemctl start backend.service
```

- `daemon-reload` makes systemd notice the new/changed unit file.
- `enable` makes it start automatically on every future boot.
- `start` runs it immediately, without rebooting.

### 3. Check status and logs

```bash
sudo systemctl status backend.service
sudo journalctl -u backend.service -f       # follow live logs
sudo journalctl -u backend.service -n 100   # last 100 lines
```

`status` shows whether it's active/enabled and the last few log lines.
`journalctl -f` tails live output (the same console/file logging already
implemented in `backend/utils/logger.py`, plus systemd's own start/stop/
restart events).

### 4. Stop, restart, disable

```bash
sudo systemctl stop backend.service       # graceful stop (SIGTERM -> lifespan shutdown)
sudo systemctl restart backend.service
sudo systemctl disable backend.service    # turn off auto-start on boot
```

### How the unit satisfies each requirement

- **Start on boot**: `[Install] WantedBy=multi-user.target` + `systemctl enable`.
- **Restart on crash**: `Restart=on-failure`, `RestartSec=3`, with
  `StartLimitIntervalSec=60` / `StartLimitBurst=5` so a persistently
  crashing process doesn't restart-loop forever — it backs off after 5
  failures within 60s and reports `failed` (visible in `status`/`journalctl`).
- **Wait for network**: `After=network-online.target` +
  `Wants=network-online.target` delay startup until the Pi's network stack
  reports a link is up (provided by `dhcpcd` or `NetworkManager`'s
  `*-wait-online` unit, both standard on Raspberry Pi OS).
- **Use the project's venv**: `ExecStart` invokes
  `.venv/bin/uvicorn` directly (the venv's own interpreter/entry point,
  not the system Python), and `PATH` is set to the venv's `bin/` for
  consistency.
- **Log failures via systemd**: `StandardOutput=journal` /
  `StandardError=journal` route everything to the journal, queryable with
  `journalctl -u backend.service`.
- **Stop gracefully**: systemd's default stop signal is `SIGTERM`
  (explicit here via `KillSignal=SIGTERM`), which uvicorn forwards into
  FastAPI's `lifespan` shutdown path — the same camera-release/peer-close
  logic verified earlier. `TimeoutStopSec=10` bounds how long systemd
  waits before escalating to `SIGKILL`, in case shutdown ever hangs.

### Verifying true "embedded device" boot behavior

1. `sudo systemctl status backend.service` — confirm `enabled` and `active (running)`.
2. Power off the Pi (`sudo poweroff`, then remove power).
3. Disconnect monitor, keyboard, and mouse.
4. Power the Pi back on and wait roughly 30-60s for boot + network + service start.
5. From a laptop/phone on the same network, open `http://<pi-ip>:8000/` —
   the live video stream should already be there with no commands run on
   the Pi.
6. Optionally confirm from another machine via SSH:
   `ssh pi@<pi-ip> 'systemctl is-active backend.service'` → should print `active`.

## Browser Usage

1. Connect your laptop/phone to the same network as the Pi (or its onboard
   access point).
2. Navigate to `http://<pi-ip>:8000/`.
3. The page auto-negotiates WebRTC on load — no button to click. The status
   panel shows peer connection state, ICE state, resolution, client-measured
   fps, and server-reported camera health/fps/active-client-count.
4. Open the same URL from a second device to confirm multi-client streaming
   (the camera is read once and fanned out via `MediaRelay`, regardless of
   client count).
5. If you kill Wi-Fi briefly and bring it back, the page reconnects on its
   own — no refresh needed. If negotiation fails outright it retries with
   backoff (1s, 2s, 5s, 5s, 10s capped).

## Debugging Guide

- **Logs**: console output plus `logs/dronai.log` (rotated at 5MB, 5 backups
  kept). Every camera open/close, peer connect/disconnect, ICE transition,
  and error logs here — this is the first place to look after a flight.
- **`GET /health`**: quick liveness + camera-healthy check, suitable for a
  watchdog/systemd healthcheck.
- **`GET /api/status`**: full JSON snapshot — measured camera fps, frame
  age, configured resolution/fps, and per-peer connection/ICE state. Poll
  this from `curl` while reproducing an issue.
- **No video, `/health` shows `camera_healthy: false`**: the capture thread
  couldn't open the device or is mid-reopen-backoff. Check
  `v4l2-ctl --list-devices` and `ls -l /dev/video*` for permissions
  (`sudo usermod -aG video $USER`, then re-login).
- **Video freezes but ICE stays `connected`**: almost always the camera
  side, not WebRTC — check `last_frame_age_seconds` in `/api/status`. The
  track will substitute a "NO CAMERA SIGNAL" placeholder frame once the
  camera has been unhealthy long enough that `get_frame()` is starved.
- **ICE stuck on `checking`**: usually a firewall/AP client-isolation issue
  blocking UDP between devices on the LAN. There's no STUN/TURN server in
  this build by design (LAN-only); confirm both devices can reach each
  other directly first (e.g. `ping`).
- **`objc[...]: Class AVFFrameReceiver is implemented in both ...` on startup**:
  cosmetic only, macOS dev-machine specific. `opencv-python-headless` and
  `av` each bundle their own copy of `libavdevice`, and macOS's Objective-C
  runtime warns about the duplicate class registration. It does not occur on
  Linux/Raspberry Pi OS (no AVFoundation/ObjC runtime involved) and has not
  caused failures in testing; safe to ignore on a dev Mac.
- **Multiple tabs interfere with each other**: they shouldn't — each gets
  its own `RTCPeerConnection`/UUID in `WebRTCManager`. If one tab's
  disconnect affects another, check `/api/status` for an unexpectedly low
  `peer_count` (would indicate a cleanup-handler bug, not a relay issue).

## Replacing the USB Webcam with the OV9281

This is intended to be a configuration change only:

1. Confirm the OV9281 enumerates as `/dev/videoN` (`v4l2-ctl --list-devices`).
2. Set `DRONAI_CAMERA_DEVICE=/dev/videoN` (or update `CameraConfig.device`'s
   default in `backend/config.py` if you want it to be the permanent default).
3. The OV9281 is a global-shutter, typically mono/raw sensor — most modules
   do not benefit from MJPEG and may not expose it at all. Set
   `DRONAI_CAMERA_MJPEG=false` and verify capture still opens; if the driver
   reports an unsupported pixel format, check `v4l2-ctl -d /dev/videoN
   --list-formats-ext` and adjust `CameraConfig` accordingly.
4. Adjust `DRONAI_CAMERA_WIDTH`/`HEIGHT`/`FPS` to the OV9281's native modes.
5. No changes are needed in `webrtc_manager.py`, `routers/webrtc.py`,
   `app.py`, or anywhere in `static/` — they only ever consume
   `Camera.get_frame()` / `Camera.config`, never talk to V4L2 directly.

## Performance Optimization Recommendations

- **MJPEG over USB**: keep `DRONAI_CAMERA_MJPEG=true` for the USB webcam.
  Uncompressed YUY2 at 720p30 (~55 MB/s) frequently exceeds USB 2.0
  bandwidth and silently caps fps; MJPEG lets the webcam do the compression
  in hardware and OpenCV decode it, which is what makes 720p30 achievable.
- **`CAP_PROP_BUFFERSIZE=1`**: already set in `camera.py` — keeps the V4L2
  driver from queuing stale frames, so `get_frame()` is always close to
  real-time instead of draining a backlog under load.
- **Zero-copy frame hand-off**: `Camera.get_frame()` returns the live
  `ndarray` reference, not a copy (safe because `cv2.read()` always
  allocates a fresh array). Don't add a `.copy()` here unless a consumer
  needs to mutate the frame in place (e.g. a future overlay step) — do the
  copy at that call site, not centrally.
- **One capture, fan-out via `MediaRelay`**: never instantiate a second
  `Camera`/`VideoCapture` per client. If you add new consumers (recording,
  YOLO inference), have them call `Camera.get_frame()` too, or subscribe to
  the same relay — don't open the device again.
- **Logging level**: `aiortc`/`aioice` are pinned to `WARNING` in
  `utils/logger.py` because their `INFO`/`DEBUG` output is extremely
  chatty and will dominate the log file otherwise.
- **CPU**: H.264 software encoding (aiortc's default via PyAV) is the
  likely bottleneck on a Pi 5 at 720p30 with multiple clients. If CPU-bound,
  the next lever is the Pi 5's hardware video encoder — that requires a
  custom aiortc encoder/codec preference and is out of scope for this
  subsystem today, but the seam is `CameraVideoStreamTrack`/the
  `RTCPeerConnection` codec negotiation, not the camera service.

## Verification Checklist

- [ ] `GET /health` returns `camera_healthy: true` with the webcam plugged in
- [ ] Browser at `http://<pi-ip>:8000/` shows live video automatically, no
      manual connect step
- [ ] Status panel shows `connected` for both peer connection and ICE state
- [ ] A second browser/device connects simultaneously and also shows live
      video, without restarting the server
- [ ] Unplugging/replugging the camera logs a reopen sequence and the
      stream recovers (or shows the NO SIGNAL placeholder) without a page
      refresh
- [ ] Stopping the server (Ctrl+C) logs every peer connection closing and
      the camera releasing — no leaked `VideoCapture`/`RTCPeerConnection`
- [ ] `/api/status` reports plausible measured fps close to the configured
      target
- [ ] Ready to integrate: `Camera` and `WebRTCManager` are constructed once
      in `app.py`'s lifespan and exposed via `app.state`, so a future
      DronAI backend can add `/telemetry`, `/mission`, `/mapping` routers
      that depend on the same instances without modifying this subsystem
