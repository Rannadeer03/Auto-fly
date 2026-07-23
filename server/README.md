# DronAI — Self-Contained Raspberry Pi 5 Drone Computer

One FastAPI backend + one website. After power-on everything happens
automatically: Wi-Fi connects, the service starts, the Pixhawk links up over
UART, the camera initialises, and the mission-planning/mapping website goes
live. No manual commands.

## Boot sequence (fully automatic)

1. Pi powers on → NetworkManager auto-connects to the Wi-Fi configured in
   `config.py` / `.env` (`WIFI_SSID` / `WIFI_PASSWORD`).
2. `deploy/wait-for-network.sh` verifies connectivity (logs the IP; never
   blocks startup if the router is off).
3. systemd starts the `dronai` service via `deploy/start.sh`.
4. The link supervisor connects to the Pixhawk on `/dev/serial0` (UART) and
   reconnects automatically whenever the heartbeat goes stale.
5. The camera capture thread starts (auto-detect, auto-reconnect).
6. Website available at `http://<pi-ip>:8000`.

## Installation (Raspberry Pi 5, no Docker)

```bash
git clone <this-repo> ~/DronAi
cd ~/DronAi
bash server/deploy/install.sh
sudo reboot
```

The installer configures Wi-Fi auto-connect (NetworkManager), enables the
UART and frees it from the serial console, adds the user to `dialout`/`video`
groups, creates `server/.venv` with `requirements.txt`, and enables the
`dronai` systemd service (auto-start on boot, always-restart).

Wire the Pixhawk TELEM port to the Pi GPIO UART: TX→GPIO15 (pin 10),
RX→GPIO14 (pin 8), GND→GND. Baud 57600 (`MAVLINK_BAUD`).

Manual run for development: `bash server/deploy/start.sh`

## Website — Vayuraksha Mission Planner (React/TypeScript, in `../web`)

A full ground-control-station SPA — this backend never renders HTML itself,
it just serves the built app (`web/dist`) and the JSON/mission APIs it calls.

- **Mission** — draw a farm boundary (rectangle/polygon), the survey
  (lawnmower grid, waypoints, capture points) regenerates live as flight
  parameters change, then Upload Mission sends it to the Pixhawk.
- **Survey Settings** — altitude, speed, overlaps, grid angle (auto or
  manual), hover-capture hold time, camera angle/format.
- **Telemetry** / **Drone Status** — live GPS, battery, attitude, link
  health, mission progress, serial port + sensor health.
- **Camera** — capture/recording status and manual controls.
- **Mission Files** — history, search, replay map, image gallery + metadata, log, ZIP export.
- **Logs** / **Settings** — live app log tail, server planning defaults.

Build it before starting the server (`web/dist` is what `/` serves):

```bash
cd web
npm install
npm run build
```

`npm run dev` runs a hot-reloading dev server on `:5173` against a backend
on `:8000` (CORS is already permissive in `main.py` for this).

## Mission automation

On `POST /start` (or the START button) a mission session begins:

- an isolated folder `missions/<Mission_Name>_<timestamp>/` is created
  (falls back to `missions/mission_<timestamp>/` if no mission name was set),
- video recording starts (disable with `RECORDING_ENABLED=0`),
- the flight plan is saved as `mission.json`,
- photo capture follows the active `CAPTURE_STRATEGY`
  (`services/capture_strategies.py`):
  - **`hover`** (default) — every survey waypoint holds position; the Pi
    waits for the airframe to be confirmed stable (ground speed and all
    three angular rates below threshold, capped at a 3s max-wait so a
    mission never stalls) before firing the shutter, then confirms the
    file actually saved before marking that waypoint captured. Exactly one
    photo per waypoint, never a duplicate, and a failed capture is logged
    and retried (same waypoint only) without aborting the mission.
  - **`continuous`** (reserved for future use) — the drone never stops;
    photos are triggered every `PHOTO_DISTANCE_M` metres of travel (or
    every `PHOTO_INTERVAL_S` seconds in `time` mode).
  
  Every photo's full metadata (position, attitude, waypoint number, capture
  sequence, drone speed, GPS fix quality, satellite count, camera
  orientation, mission name/ID, sharpness scores, checksum) is accumulated
  during the flight and written to `metadata.json`/`metadata.csv` at the
  end — the same record is embedded as EXIF/GPS metadata directly into each
  JPEG (`EXIF_ENABLED`), so photos stay usable in GIS tools even without the
  sidecar files. A thumbnail is generated alongside each full-resolution
  photo for the frontend gallery.

  Each capture is scored on sharpness (`services/image_quality.py` —
  variance-of-Laplacian, Tenengrad, Brenner, edge density, combined into one
  confidence score) and retried up to `CAPTURE_RETRY_LIMIT` times if it
  comes out blurry; the best frame seen is kept either way, so a mission
  never skips a waypoint's shot outright.

  Before AUTO mode is allowed, `POST /start` runs a pre-flight camera
  validation burst (`services/camera_validation.py`): captures
  `CAMERA_VALIDATION_FRAME_COUNT` frames from the live feed, and blocks
  mission start (`CAMERA_VALIDATION_ENABLED`) if the sharpest one never
  clears `QUALITY_CONFIDENCE_THRESHOLD`, retrying the whole burst up to
  `CAMERA_VALIDATION_RETRY_LIMIT` times first.
- when the vehicle disarms (mission finished), recording stops and all files
  are finalised.

Mission folder layout:

```
missions/<Mission_Name>_<timestamp>/
├── video.mp4
├── images/
│   ├── photo_00001.jpg …
│   └── thumbs/photo_00001_thumb.jpg …
├── logs/mission.log
├── telemetry.json
├── metadata.json        # mission summary + full per-image metadata array
├── metadata.csv          # per-image metadata, flattened
└── mission.json          # the flight plan that was executed
```

## API

| Method | Path | Description |
|---|---|---|
| GET | `/` | The website |
| GET | `/health` | Overall health |
| POST | `/connect`, `/disconnect` | Manual Pixhawk link control (auto by default) |
| GET | `/ports` | List candidate serial ports |
| POST | `/upload` | Upload `.plan` / `.waypoints` mission file |
| POST | `/mission/generate` | Generate + upload survey grid from polygon |
| GET | `/config` | Mission-planning defaults for the frontend |
| GET | `/mission` | Current mission status |
| POST | `/clear` | Clear mission |
| GET | `/telemetry` | Telemetry snapshot (1 Hz poll) |
| POST | `/arm`, `/disarm`, `/start`, `/pause`, `/resume`, `/rtl`, `/land`, `/emergency_stop` | Flight commands |
| GET | `/camera/status` | Camera + recording status (incl. frozen-frame flag) |
| GET | `/camera/capabilities` | What the camera/driver actually reports (resolution, fps, autofocus support) |
| POST | `/camera/photo` | Manual photo |
| POST | `/camera/recording/start`, `/camera/recording/stop` | Manual recording |
| GET | `/missions` | Mission history |
| GET | `/missions/{name}` | One mission's full results |
| GET | `/mission/session` | Active automation session status |
| GET | `/missions-data/…` | Static mission outputs (photos, video, JSON) |
| GET/DELETE | `/logs` | Application logs |

## Configuration — all in `config.py`

Nothing is hardcoded. Values resolve in priority order: **process
environment → `server/.env` file → `config.py` defaults**. Copy
`server/.env.example` to `server/.env` to override locally without touching
source.

| Variable | Default | Meaning |
|---|---|---|
| `WIFI_SSID` / `WIFI_PASSWORD` | `Coconut_ufi_97233` / … | Wi-Fi applied by install.sh |
| `MAVLINK_PORT` | `/dev/serial0` (Linux) | Pixhawk UART device |
| `MAVLINK_BAUD` | `57600` | UART baud rate |
| `LINK_STALE_S` | `10` | Heartbeat staleness before auto-reconnect |
| `CAMERA_DEVICE` | `auto` | USB camera (`auto` scans /dev/video*) |
| `CAMERA_HFOV_DEG` / `CAMERA_VFOV_DEG` | `62.2` / `48.8` | Lens FOV for overlap math |
| `CAMERA_PITCH_DEG` | `-90` | Fixed camera mounting angle (no gimbal); recorded into every photo's metadata |
| `CAPTURE_STRATEGY` | `hover` | `hover` (position-hold-and-shoot) or `continuous` (reserved) |
| `HOVER_HOLD_TIME_S` | `1.0` | Seconds ArduCopter loiters at each survey waypoint |
| `PHOTO_CAPTURE_MODE` | `distance` | `distance` or `time` — only used when `CAPTURE_STRATEGY=continuous` |
| `PHOTO_DISTANCE_M` | `10` | Metres between mapping photos (continuous mode) |
| `PHOTO_INTERVAL_S` | `2` | Seconds between photos (continuous + time mode) |
| `RECORDING_ENABLED` | `1` | Record video during missions |
| `MIN_BATTERY_VOLTAGE` / `MIN_BATTERY_PERCENT` | `22.2` / `20` | Below this, ARM is rejected |
| `MIN_GPS_SATELLITES` / `REQUIRED_GPS_FIX` | `6` / `3` | Below this, ARM/AUTO is rejected |
| `QUALITY_CONFIDENCE_THRESHOLD` | `0.35` | Min. combined sharpness confidence (0..1) for a capture to be accepted |
| `CAPTURE_RETRY_LIMIT` | `2` | Per-waypoint retries when a capture scores below threshold |
| `CAMERA_VALIDATION_ENABLED` | `1` | Block `POST /start` (AUTO) if pre-flight camera validation fails |
| `CAMERA_VALIDATION_FRAME_COUNT` / `_RETRY_LIMIT` | `10` / `1` | Validation burst size / retry attempts before failing |
| `CAMERA_FROZEN_FRAME_THRESHOLD` | `15` | Consecutive identical frames before the capture thread forces a reopen |
| `EXIF_ENABLED` | `1` | Embed GPS/mission/quality metadata as EXIF into every captured JPEG |
| `DEFAULT_ALTITUDE_M` / `DEFAULT_SPEED_MS` | `30` / `5` | Planning defaults |
| `DEFAULT_SIDE_OVERLAP_PCT` / `DEFAULT_FRONT_OVERLAP_PCT` | `65` / `75` | Overlap defaults |
| `MISSIONS_DIR` | `server/missions` | Mission output root |
| `PORT` | `8000` | HTTP port |
