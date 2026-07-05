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
- **Mission Files** — history, search, replay map, photos, log, ZIP export.
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

- an isolated folder `missions/mission_<timestamp>/` is created,
- video recording starts (disable with `RECORDING_ENABLED=0`),
- the flight plan is saved as `mission.json`,
- the drone flies the mission normally — it is **never paused**. Photos are
  captured continuously for mapping, every `PHOTO_DISTANCE_M` metres of
  travel (or every `PHOTO_INTERVAL_S` seconds in `time` mode). Each photo is
  geotagged from live telemetry into `mapping/photos.json`.
- when the vehicle disarms (mission finished), recording stops and all files
  are finalised.

Mission folder layout:

```
missions/mission_<timestamp>/
├── video.mp4
├── photos/photo_00001.jpg …
├── logs/mission.log
├── telemetry.json
├── metadata.json
├── mission.json
└── mapping/photos.json
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
| GET | `/camera/status` | Camera + recording status |
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
| `PHOTO_CAPTURE_MODE` | `distance` | `distance` or `time` |
| `PHOTO_DISTANCE_M` | `10` | Metres between mapping photos |
| `PHOTO_INTERVAL_S` | `2` | Seconds between photos (time mode) |
| `RECORDING_ENABLED` | `1` | Record video during missions |
| `DEFAULT_ALTITUDE_M` / `DEFAULT_SPEED_MS` | `30` / `5` | Planning defaults |
| `DEFAULT_SIDE_OVERLAP_PCT` / `DEFAULT_FRONT_OVERLAP_PCT` | `65` / `75` | Overlap defaults |
| `MISSIONS_DIR` | `server/missions` | Mission output root |
| `PORT` | `8000` | HTTP port |
