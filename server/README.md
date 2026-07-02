# DronAI Unified Server

One FastAPI application for the Raspberry Pi 5 that combines:

- **Drone control** (from `Autoflight/`): Pixhawk auto-connect with serial port
  auto-detection, mission upload/verification (`.plan` / `.waypoints`),
  mission execution, flight commands, telemetry.
- **Camera** (from `Webcam/`): USB camera auto-detection, threaded capture with
  automatic reconnect, WebRTC live streaming, video recording, photo capture.
- **Mission automation** (new): when a mission starts, recording starts
  automatically; at every reached waypoint the drone holds ~2 s and one photo
  is captured; when the mission finishes (vehicle disarms), recording stops
  and telemetry/metadata are written.

## Layout

```
server/
├── main.py                  # FastAPI entry point
├── config.py                # all settings (env-overridable)
├── api/                     # HTTP routes (drone + camera + missions)
├── mavlink/                 # MAVLink connection, upload, commands, health
├── parser/                  # .plan / .waypoints parsers
├── models/                  # Pydantic models
├── services/                # DroneService-layer singletons:
│   ├── connection_service.py    #   Pixhawk connect lifecycle
│   ├── mission_service.py       #   mission file handling + upload
│   ├── telemetry_service.py     #   telemetry snapshots
│   ├── camera_service.py        #   USB capture (auto-detect, auto-reconnect)
│   ├── streaming_service.py     #   WebRTC live stream (independent of recording)
│   ├── recording_service.py     #   mp4 recording
│   ├── storage_service.py       #   missions/ folder layout
│   └── mission_runner.py        #   mission automation
├── missions/                # per-mission output (created at runtime)
│   └── mission_<timestamp>/
│       ├── video.mp4
│       ├── images/waypoint_NNN.jpg
│       ├── telemetry.json
│       └── metadata.json
└── deploy/                  # systemd unit + install/start scripts
```

## Installation (Raspberry Pi 5, no Docker)

```bash
git clone <this-repo> ~/DronAi        # or copy the repo to the Pi
cd ~/DronAi
bash server/deploy/install.sh         # system deps, venv, permissions, systemd
sudo systemctl start dronai
journalctl -u dronai -f               # watch logs
```

The installer adds your user to `dialout` (Pixhawk serial) and `video`
(camera) groups, creates `server/.venv`, installs `requirements.txt`, and
installs/enables the `dronai` systemd service (auto-start on boot,
auto-restart on failure).

Manual run (development):

```bash
bash server/deploy/start.sh
# or: cd server && uvicorn main:app --host 0.0.0.0 --port 8000
```

## API

Drone (unchanged from Autoflight):

| Method | Path | Description |
|---|---|---|
| GET | `/ports` | List candidate Pixhawk serial ports |
| POST | `/connect` | Connect to Pixhawk (auto-detects port) |
| POST | `/disconnect` | Disconnect |
| POST | `/upload` | Upload `.plan` / `.waypoints` mission file |
| GET | `/mission` | Mission status |
| POST | `/clear` | Clear mission |
| GET | `/telemetry` | Full telemetry snapshot (poll at 1 Hz) |
| POST | `/arm`, `/disarm` | Arm / disarm |
| POST | `/start` | Start mission (AUTO) — **also starts mission automation** |
| POST | `/pause`, `/resume` | Pause (LOITER) / resume (AUTO) |
| POST | `/rtl`, `/land`, `/emergency_stop` | Safety commands |
| GET/DELETE | `/logs` | Recent app logs |

Camera / streaming / recording:

| Method | Path | Description |
|---|---|---|
| GET | `/camera/status` | Camera + streaming + recording status |
| POST | `/camera/photo` | Capture one photo |
| POST | `/camera/recording/start` | Start manual recording |
| POST | `/camera/recording/stop` | Stop manual recording |
| POST | `/offer` | WebRTC signaling (same contract as Webcam backend) |
| GET | `/api/status` | Webcam-backend-compatible status |
| GET | `/stream` | Browser live-view page |

Missions / storage:

| Method | Path | Description |
|---|---|---|
| GET | `/missions` | List stored mission folders |
| GET | `/mission/session` | Active mission-automation session status |
| GET | `/health` | Overall health (drone, camera, recording, session) |

Web UI: `http://<pi>:8000/` (mission control), `http://<pi>:8000/stream`
(live video).

## Configuration (environment variables)

All defaults work out of the box on a Pi. Common overrides:

| Variable | Default | Meaning |
|---|---|---|
| `MAVLINK_PORT` | `auto` | Pixhawk serial port (`auto` scans /dev/ttyACM*, /dev/ttyUSB*) |
| `MAVLINK_BAUD` | `57600` | Serial baud rate |
| `DRONE_AUTO_CONNECT` | `1` | Connect to Pixhawk automatically at startup, keep retrying |
| `CAMERA_DEVICE` | `auto` | `auto` scans /dev/video*; or e.g. `/dev/video0` |
| `CAMERA_WIDTH`/`CAMERA_HEIGHT`/`CAMERA_FPS` | `1280`/`720`/`30` | Capture profile |
| `WAYPOINT_HOLD_SECONDS` | `2.0` | Hold time at each waypoint before the photo |
| `MISSIONS_DIR` | `server/missions` | Where mission folders are written |
| `PORT` | `8000` | HTTP port |

## Behavior notes

- **Streaming is independent from recording.** Both read the latest frame
  from the shared camera service; a WebRTC failure never affects recording,
  the mission, or the camera thread.
- **Camera disconnects** are handled by the capture thread with backoff
  reopen; an active recording stays open and resumes writing when the camera
  returns.
- **Mission completion** is detected when the vehicle disarms (the reliable
  end-of-mission signal for ArduPilot missions ending in RTL/LAND).
  Recording also stops on connection loss or server shutdown, and
  `telemetry.json` / `metadata.json` are always written.
