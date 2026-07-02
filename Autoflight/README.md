# Mission Planner v1.0

Agricultural drone mission control interface.
Runs on a **Raspberry Pi 5**, communicates with a **Pixhawk 2.4.8** via USB/MAVLink,
and is accessed from any browser on the local network.

---

## Architecture

```
Browser  ──REST──▶  FastAPI (Pi 5)  ──MAVLink/USB──▶  Pixhawk 2.4.8  ──▶  Drone
```

The browser never touches MAVLink. The Raspberry Pi owns all logic.
The Pixhawk only flies, stabilises, and executes uploaded missions.

---

## Requirements

- Raspberry Pi 5 running Linux
- Python 3.11+
- Pixhawk 2.4.8 connected via `/dev/ttyACM0` at 57 600 baud

---

## Quick Start

```bash
# On the Raspberry Pi
cd backend
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

Then open `http://<pi-ip>:8000` in any browser on the same network.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MAVLINK_PORT` | `/dev/ttyACM0` | Serial port for Pixhawk |
| `MAVLINK_BAUD` | `57600` | Baud rate |
| `MAVLINK_TIMEOUT` | `10.0` | Heartbeat wait timeout (s) |
| `MIN_BATTERY_VOLTAGE` | `22.2` | Minimum voltage to arm (V) |
| `MIN_BATTERY_PERCENT` | `20` | Minimum battery % to arm |
| `MIN_GPS_SATELLITES` | `6` | Minimum satellites to arm |
| `REQUIRED_GPS_FIX` | `3` | Minimum GPS fix type (3 = 3D) |
| `LOG_LEVEL` | `INFO` | Python log level |
| `PORT` | `8000` | HTTP server port |

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web UI |
| `GET` | `/health` | Server health check |
| `POST` | `/connect` | Open MAVLink connection |
| `POST` | `/disconnect` | Close MAVLink connection |
| `POST` | `/upload` | Upload `.waypoints` file |
| `GET` | `/mission` | Mission status |
| `POST` | `/clear` | Clear mission from vehicle |
| `GET` | `/telemetry` | Live drone telemetry |
| `POST` | `/arm` | Arm the drone |
| `POST` | `/disarm` | Disarm the drone |
| `POST` | `/start` | Start mission (AUTO mode) |
| `POST` | `/pause` | Pause mission (LOITER) |
| `POST` | `/resume` | Resume mission (AUTO) |
| `POST` | `/rtl` | Return to Launch |
| `POST` | `/land` | Land in place |
| `POST` | `/emergency_stop` | Force-disarm immediately |
| `GET` | `/logs` | Recent application logs |

---

## Mission File Format

Only **QGroundControl Waypoint** files (`.waypoints`) are accepted.

```
QGC WPL 110
0   1   0   16  0   0   0   0   -33.867  151.207  100.0  1
1   0   3   16  0   0   0   0   -33.868  151.208  50.0   1
```

---

## Safety Checks

**Before ARM:** connected, heartbeat OK, battery ≥ threshold, GPS fix ≥ 3D,
satellites ≥ 6, mission loaded.

**Before AUTO:** armed, mission loaded, EKF healthy, GPS OK, heartbeat OK.

**Emergency Stop:** unconditional force-disarm — no checks, no delay.

---

## Project Structure

```
backend/
├── app.py                  FastAPI entry point
├── config.py               Settings
├── requirements.txt
├── api/
│   ├── connect.py          POST /connect /disconnect
│   ├── mission.py          POST /upload /clear  GET /mission
│   ├── telemetry.py        GET /telemetry
│   └── commands.py         POST /arm /disarm /start /pause /resume /rtl /land /emergency_stop
├── services/
│   ├── connection_service.py
│   ├── mission_service.py
│   ├── telemetry_service.py
│   └── log_service.py
├── mavlink/
│   ├── connection.py       DroneState + MAVLinkConnection singleton
│   ├── commands.py         MAVLinkCommands
│   ├── mission_upload.py   Upload protocol
│   ├── telemetry.py        Snapshot builder
│   └── health.py           Pre-flight safety checks
├── parser/
│   └── waypoint_parser.py  QGC WPL 110 parser
├── models/
│   ├── mission.py          Pydantic models
│   └── telemetry.py        Pydantic models
├── templates/
│   └── index.html          Single-page UI
├── static/
│   ├── js/app.js           Frontend application
│   └── css/custom.css
├── uploads/missions/       Saved .waypoints files
└── logs/                   Rotating log files
```
