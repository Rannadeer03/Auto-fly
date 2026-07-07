# PROJECT_CONTEXT

## Repository
- Path: `/Users/rannadeerkumar/Desktop/DronAi`
- Remote: `origin` → `https://github.com/Rannadeer03/Auto-fly.git`

## Branch / Commit
- Branch: `mission-history`
- HEAD: `9ee2fc7` — "feat: implement Phase 2 manual mission planner UI"

## Frameworks
- **Backend**: FastAPI (Python 3.11+), Uvicorn, Pydantic v2, `pymavlink`/`pyserial` (MAVLink/UART), OpenCV headless (camera)
- **Frontend**: React 19 + TypeScript, Vite 8, Tailwind CSS v4, Zustand (state), TanStack Query (server state), MapLibre GL + Terra Draw (mapping), React Hook Form + Zod (forms/validation), Radix UI primitives, Framer Motion

## Languages
- Python (`server/`)
- TypeScript/TSX (`web/`)

## Entry Points
- Backend: `server/main.py` (FastAPI app, `uvicorn main:app`); systemd unit `server/deploy/dronai.service` via `server/deploy/start.sh`
- Frontend: `web/src/main.tsx` → `web/src/App.tsx`; built to `web/dist` and served as a static SPA shell by `server/main.py`'s `GET /`

## Folder Structure (depth 3)
```
server/
  api/            camera, commands, connect, mission, missions, mission_library, telemetry
  mavlink/        connection, commands, health, mission_upload, telemetry
  models/         mission, manual_mission, telemetry
  parser/         loader, plan_parser, plan_writer, waypoint_parser
  services/       camera, capture_strategies, connection, grid_planner, log,
                  manual_mission_builder, mission_enrichment, mission_library,
                  mission_runner, mission_watchdog, recording, storage, telemetry
  deploy/         install.sh, start.sh, wait-for-network.sh, generate-cert.sh, dronai.service
  uploads/missions/, mission_library/ (created at runtime)

web/
  src/
    pages/        drone-status, settings, logs, mission-files, mission, camera, telemetry, mission-library
    features/     camera, logs, manual-mission, map, mission-execution,
                  mission-history, mission-library, survey, telemetry
    components/   layout, feedback, ui
    store/        mission-draft-store, ui-store, geolocation-store
    services/     api-client, query-client + one service per domain (mission, telemetry, camera, logs, commands, connection, mission-history, mission-library)
```

## High-Level Architecture
Single self-contained Raspberry Pi 5 "drone computer": one FastAPI process owns the Pixhawk UART link, the USB camera, and mission storage, and serves a prebuilt React SPA ("Vayuraksha Mission Planner") from the same origin. The React app uses no client-side routing — navigation is Zustand state (`ui-store.ts`), keeping `/` collision-free with the JSON API. On boot, `main.py`'s `lifespan` starts three background daemons: a camera capture thread, a Pixhawk link supervisor (auto-connect/reconnect), and a GCS-independent mission watchdog.

## Mission Flow
Two planning modes share one map surface (`MissionPage`):
- **Survey**: draw a farm polygon → `grid_planner.py` auto-generates a lawnmower grid (live, on every parameter change).
- **Manual**: place Takeoff/Waypoint/Loiter/RTL/Land items directly → `manual_mission_builder.py` assembles them in the given order.
Both paths converge on a `Mission` model, get densified/enriched (`mission_enrichment.py` inserts loiter/capture items), then upload via MAVLink. Plans can be saved/reused via the Mission Library (distinct from post-flight Mission History/storage).

## MAVLink Flow
`mavlink/connection.py` owns the serial link and a background receiver thread with per-message "waiter queues" so protocol exchanges (upload, verification, command ACKs) never race the telemetry dispatcher. `mavlink/mission_upload.py` implements the standard GCS→Vehicle MISSION_COUNT/MISSION_REQUEST_INT/MISSION_ITEM_INT/MISSION_ACK handshake plus read-back verification and mission download. `mavlink/commands.py` issues ARM/DISARM/AUTO/LOITER/RTL/LAND mode changes; `mission_watchdog.py` polls telemetry independently of this app's own POST /start so recording/capture still trigger if AUTO was entered via RC switch or QGroundControl directly.

## Camera Flow
`camera_service.py` runs a persistent capture thread (auto-detect `/dev/video*`, auto-reconnect). During an active mission, a pluggable `CaptureStrategy` (`capture_strategies.py`) decides when to shoot: default `HoverCaptureStrategy` waits for position/altitude/stability confirmation at each capture waypoint (keyed off `MAV_CMD_NAV_LOITER_TIME` completion) before triggering exactly one photo; `ContinuousCaptureStrategy` (distance/time-based, no hover) exists but is reserved for future use. `recording_service.py` records video for the session; `storage_service.py` writes the full per-mission folder (photos, thumbs, video, telemetry.json, metadata.json/csv, mission.json, index.json).

## Current Development Phase
**Phase 2 — Manual Mission Planner UI** (latest commit). Survey Mode, Mission Library, Mission History, and core MAVLink/camera automation are implemented and hardened (prior commits: hover-capture, safety, HTTPS-for-geolocation). Manual Mode's mission-item list, upload, and inspector UI just landed; drag-reorder/insert is explicitly deferred ("Phase 2B+", per `ui-store.ts`), and Change Speed / Trigger Distance manual items are persisted but not yet sent to the vehicle.
