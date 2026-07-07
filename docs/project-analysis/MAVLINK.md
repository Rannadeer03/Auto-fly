# MAVLINK

## Pixhawk
Pixhawk 2.4.8 connected via UART to the Raspberry Pi 5 GPIO header (TX→GPIO15/pin10, RX→GPIO14/pin8, GND→GND), `/dev/serial0` at 57600 baud (`config.py`: `MAVLINK_PORT`, `MAVLINK_BAUD`). On non-Linux dev machines, `MAVLINK_PORT="auto"` scans USB ports instead. `mavlink/connection.py`'s `MAVLinkConnection` owns the single serial connection and a background receiver thread. Connect timeout is generous (`MAVLINK_TIMEOUT=15s`) because the Pixhawk 2.4.8 can take 15+ seconds to boot and send its first heartbeat.

**Waiter-queue design**: protocol exchanges (mission upload, command ACKs, mission verification) need exclusive access to specific incoming message types. The receiver thread routes any message type with a registered waiter into that waiter's queue instead of normal telemetry dispatch (`register_waiter()`/`unregister_waiter()`), eliminating a prior race where the receiver consumed `MISSION_REQUEST_INT`/`COMMAND_ACK` before the protocol handler could read them.

`main.py`'s link supervisor thread runs for the process lifetime: connects if not connected, and tears down + reconnects if heartbeat is stale for `LINK_STALE_S` (10s default), retrying every `DRONE_AUTO_CONNECT_RETRY_S` (5s). It shares `ConnectionService` with `POST /connect` so manual and automatic connects can't race into a duplicate connection.

## Telemetry
`mavlink/telemetry.py` maintains the shared `DroneState`/`TelemetryData` from the receiver thread. `TELEMETRY_STREAM_RATE_HZ` (default 4) is requested explicitly via `REQUEST_DATA_STREAM` right after connect — ArduPilot only sends HEARTBEAT by default, so GPS/position/status require this explicit request (mirrors what every GCS, including QGroundControl, does). `GET /telemetry` exposes the live snapshot. An optional `LOG_TELEMETRY_RX` debug flag (temporary, flagged for removal) logs every received HEARTBEAT/GPS_RAW_INT/GLOBAL_POSITION_INT/MISSION_CURRENT at INFO level for comparison against QGroundControl.

## Mission Upload
`mavlink/mission_upload.py`, standard ArduPilot handshake:
1. GCS → `MISSION_COUNT(n)`
2. Vehicle → `MISSION_REQUEST_INT(seq)` (repeated per item)
3. GCS → `MISSION_ITEM_INT(seq)` (always answers the requested seq)
4. Vehicle → `MISSION_ACK(ACCEPTED)`

All I/O goes through `connection.register_waiter()` — direct `master.recv_match()` calls are disallowed by convention to avoid races with the background receiver.

## Mission Download
Same module: `MISSION_REQUEST_LIST` → `MISSION_COUNT(n)` → per-item `MISSION_REQUEST_INT(i)`/`MISSION_ITEM_INT(i)` read-back. Used both for post-upload verification (compares every field against the in-memory `Mission`) and by `mission_watchdog.py` to reconstruct the flight plan when AUTO is detected but this backend never uploaded a mission itself (e.g. QGroundControl uploaded directly).

## AUTO Detection
`services/mission_watchdog.py` polls `drone_state` every 0.5s independent of this app's own `POST /start`. When `armed && flight_mode == "AUTO"` and no session is already active, it starts one — downloading the mission from the vehicle first if `mission_service.current_mission` is empty. This makes recording/capture automation trigger identically whether AUTO was entered via this app's Start button, an RC transmitter mode switch, or QGroundControl connected directly.

## RTL
`POST /rtl` (`api/commands.py`) → `mavlink/commands.py`'s `rtl()` → ArduCopter RTL flight-mode change, after a `check_connected` health gate.

## Camera Trigger
Not a MAVLink camera command — capture is host-side. `services/capture_strategies.py`'s `HoverCaptureStrategy` keys the shutter off `MISSION_ITEM_REACHED` for a dedicated `MAV_CMD_NAV_LOITER_TIME` item inserted after each capture waypoint by `mission_enrichment.py` (ArduCopter only reports `MISSION_ITEM_REACHED` for a LOITER_TIME item once its hold duration has actually elapsed), plus its own position/altitude/stability confirmation before calling into `camera_service`.

## Recording Trigger
Also host-side, not MAVLink-driven: `mission_runner.py` starts/stops `recording_service.py` at session start/end (mission start detected via `on_mission_started`, from either `POST /start` or the watchdog).

## Mission Completion
`MissionRunner` ends a session on vehicle disarm or connection loss (`main.py`'s shutdown path also force-ends any active session). On end: recording stops, and `telemetry.json`, `metadata.json`, and `metadata.csv` are written to the session's storage folder alongside the photos/video already captured during flight.
