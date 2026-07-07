# BACKEND

Single FastAPI process (`server/main.py`), Python 3.11+, serving both the JSON API and the built React SPA (`web/dist`) from one origin.

## FastAPI
`app = FastAPI(...)`, permissive CORS (`allow_origins=["*"]`, for LAN dev access). `lifespan` context manager: creates `uploads/`, `logs/`, `missions/` dirs; starts the camera thread, the Pixhawk link-supervisor thread (if `DRONE_AUTO_CONNECT`), and the mission watchdog thread; on shutdown, stops any active mission session, recording, and camera, and disconnects MAVLink cleanly. Static mounts: `/assets` (SPA JS/CSS) and `/missions-data` (browsable per-mission media). Core routes: `GET /` (SPA shell, 503 placeholder if unbuilt), `GET /health`, `GET/DELETE /logs`. Routers included: `connect`, `mission`, `telemetry`, `commands`, `camera`, `missions`, `mission_library`.

## Services (`server/services/`)
| Service | Responsibility |
|---|---|
| `grid_planner.py` | Lawnmower survey grid generation from a farm polygon + flight params |
| `manual_mission_builder.py` | Assembles ordered Takeoff/Waypoint/Loiter/RTL/Land items into a `Mission` (no algorithm — order is verbatim) |
| `mission_enrichment.py` | Densifies long legs, inserts `MAV_CMD_NAV_LOITER_TIME` capture items — applied uniformly to every mission (uploaded file or generated) before upload |
| `mission_service.py` | Tracks the currently-loaded mission (uploaded/generated) |
| `mission_runner.py` | Owns the lifecycle of one active mission *session*: creates the storage folder, starts recording, drives the capture-strategy monitor thread, writes telemetry/metadata on completion |
| `mission_watchdog.py` | GCS-independent: polls telemetry for AUTO+armed and starts a session even if this backend didn't trigger it (RC switch or QGroundControl) |
| `capture_strategies.py` | `HoverCaptureStrategy` (default — wait for position/stability, one photo per capture waypoint) and `ContinuousCaptureStrategy` (distance/time-triggered, reserved for future use) |
| `mission_library_service.py` | CRUD for reusable saved mission *plans* (distinct from post-flight records) |
| `camera_service.py` | Persistent capture thread, auto-detect/reconnect USB camera |
| `recording_service.py` | Video recording start/stop for a mission session |
| `storage_service.py` | On-disk mission folder layout, ZIP export, path-traversal-safe name validation |
| `connection_service.py` | Wraps MAVLink connect/disconnect, shared by the API and the link supervisor to prevent double-connects |
| `log_service.py` | In-memory rolling log buffer surfaced via `GET /logs` |

## Mission Generation
`POST /mission/generate` (survey, `grid_planner.py`) and `POST /mission/generate-manual` (manual, `manual_mission_builder.py`) in `api/missions.py`, both returning a `GridResponse` (waypoints + stats). `GET /config` exposes planning defaults (altitude, speed, overlaps, grid angle) to the frontend.

## Mission Upload
`POST /upload` (`api/mission.py`) accepts `.waypoints`/`.plan` files (`parser/plan_parser.py`, `parser/waypoint_parser.py`) or a generated `Mission`; `mavlink/mission_upload.py` performs the MISSION_COUNT → MISSION_REQUEST_INT → MISSION_ITEM_INT → MISSION_ACK handshake, then reads back and verifies every field. `.plan` files can also be written back out (`parser/plan_writer.py`) for round-tripping with QGroundControl.

## Mission Execution
`api/commands.py`: ARM (gated by `HealthChecker.check_arm_ready` — link + mission loaded only), START (mode→AUTO, then `mission_runner.on_mission_started`), PAUSE (→LOITER), RESUME (→AUTO), RTL, LAND, DISARM, emergency-stop. Every handler validates state via `mavlink/health.py` first and returns a structured `ApiResponse` with a failure reason on rejection — GPS/battery/EKF are surfaced to the operator but never block commands (ArduPilot/QGC remain the flight-safety authority).

## Telemetry
`GET /telemetry` (`api/telemetry.py`) returns the live `TelemetryData` snapshot maintained by `mavlink/telemetry.py` from the background MAVLink receiver thread (GPS, battery, attitude, mode, armed state, link health). Stream rate requested explicitly via `REQUEST_DATA_STREAM` on connect (`TELEMETRY_STREAM_RATE_HZ`).

## Camera
`api/camera.py`: `GET /camera/status`, `POST /camera/photo` (manual capture), `POST/POST /camera/recording/{start,stop}`. Device selection is `CAMERA_DEVICE=auto` (scans `/dev/video*` on Linux, falls back to index 0).

## Recording
`recording_service.py`, started/stopped by `mission_runner.py` per session (`RECORDING_ENABLED`); output is `video.mp4` inside the mission's storage folder.

## Storage
Per-flight folders under `MISSIONS_DIR` (`server/missions/`): `<Name>_<timestamp>/{video.mp4, images/, images/thumbs/, logs/mission.log, telemetry.json, metadata.json, metadata.csv, mission.json, index.json}`. Separately, `MISSION_LIBRARY_DIR` (`server/mission_library/`) holds one JSON file per saved *plan* (pre-flight). Name format is regex-validated (`^[A-Za-z0-9_\-]+_\d{8}_\d{6}(_\d+)?$`) to make path traversal through the API impossible.

## Configuration (`server/config.py`)
Single `Settings` class, env-first (`os.environ` → `server/.env` → hardcoded default). Covers Wi-Fi, MAVLink port/baud/timeouts/auto-reconnect, safety thresholds (min battery V/%, min GPS sats, required fix type — surfaced, not enforced, on ARM/AUTO), camera (device/resolution/FPS/FOV/mount pitch), mission automation (capture strategy, hover hold time, waypoint/altitude tolerances, max waypoint spacing), mission-planning defaults exposed to the frontend, storage paths, upload limits, logging, server host/port, and self-signed HTTPS cert paths (`deploy/generate-cert.sh`) needed for the browser Geolocation API to work over plain LAN HTTP.
