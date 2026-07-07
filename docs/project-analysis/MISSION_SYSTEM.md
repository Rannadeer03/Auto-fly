# MISSION_SYSTEM

## Mission Planning
One map surface (`MissionPage`) hosts two mutually-exclusive planning modes (`useUiStore().missionMode`); switching mode resets the other mode's draft (`useMissionDraftStore().reset()`). Both modes converge on the same backend `Mission` model and the same enrichment/upload pipeline.

## Survey Planner
Frontend: draw a farm polygon (`farm-draw-tool.tsx`, Terra Draw) → `use-auto-generate-survey.ts` calls `POST /mission/generate` on every parameter change (altitude, speed, side/front overlap, grid angle, capture mode) for a live-updating lawnmower grid. Backend: `services/grid_planner.py` computes the grid from the polygon + camera footprint (HFOV/VFOV/altitude); home/launch point is always the connected vehicle's actual position, or the planned home — never a survey waypoint.

## Manual Planner
Frontend: `manual-mission-tool.tsx`/`manual-mission-layer.tsx` — click to place Takeoff, Waypoint, Loiter, RTL, Land items in order; `mission-inspector.tsx` edits the list; `mission-settings-panel.tsx` sets mission-level options (Change Speed, Trigger Distance — currently persisted only, not yet sent to the vehicle). `use-generate-manual-mission.ts` calls `POST /mission/generate-manual`. Backend: `services/manual_mission_builder.py` assembles the ordered item list verbatim into a `Mission` — no path-planning algorithm, unlike the survey grid. Adding a new mission-item type requires one dataclass + one `_emit_item()` branch, nothing else.

## Mission Library
Reusable, pre-flight *plans* (polygon/items + params + generated waypoints), stored one-JSON-file-per-plan under `MISSION_LIBRARY_DIR` (`services/mission_library_service.py`). Deliberately separate from post-flight session storage. API (`api/mission_library.py`): save (survey or manual variant), list/search, detail, rename, duplicate, delete, download (as `.plan`), and "deploy" (re-upload straight to the vehicle). Frontend: `features/mission-library/` + `mission-library-page.tsx`.

## Mission History
Post-flight session records under `MISSIONS_DIR`, auto-indexed (`storage_service.py` writes `index.json` per session). API (`api/missions.py`): `GET /missions` (search), `GET /missions/{name}` (detail), `/{name}/log`, `/{name}/download` (ZIP streaming), `DELETE /{name}`, plus `GET /mission/session` for the currently-active session. Frontend: `features/mission-history/` rendered by `mission-files-page.tsx` — list, detail panel, flight replay map (`mission-replay-map.tsx`), image gallery + metadata, log tail, ZIP export.

## .plan Generation
`parser/plan_writer.py` converts an internal `Mission` into a standard QGC v1/v2 `.plan` JSON document (`mission_to_plan_dict`) — waypoint 0 (home, `current=True`) becomes `plannedHomePosition`, the rest become `SimpleItem`s with `command=16` (NAV_WAYPOINT). Used for Mission Library "download" so saved plans open directly in QGroundControl.

## QGroundControl
Interop is two-way: `parser/plan_parser.py` reads QGC `.plan` files (`POST /upload` in `api/mission.py`) — `SimpleItem`s only in this version, `ComplexItem` (survey/corridor) is skipped; `plan_writer.py` writes them back out, so a plan round-trips between this app and QGroundControl. QGroundControl connected directly to the Pixhawk (bypassing this app entirely) is explicitly supported: `mission_watchdog.py` detects AUTO+armed regardless of trigger source and downloads the mission from the vehicle if this backend never uploaded one itself.

## Pixhawk
Physical link: Pixhawk 2.4.8 TELEM port ↔ Raspberry Pi 5 GPIO UART (`/dev/serial0`, 57600 baud) — see MAVLINK.md for protocol detail.

## Mission Execution
`api/commands.py` START issues a mode change to AUTO, then calls `mission_runner.on_mission_started(...)`; every command handler pre-validates via `mavlink/health.py` (link + mission-loaded only — GPS/battery/EKF are surfaced, not enforced). `mission_watchdog.py` independently starts the same session lifecycle if AUTO+armed is observed without this app having triggered it.

## AUTO Mode
`MissionRunner` (`services/mission_runner.py`) is the session owner while the vehicle flies AUTO: creates the isolated mission folder, starts recording, runs a capture-strategy monitor thread (`_MONITOR_POLL_S = 0.2s`) that ticks the active `CaptureStrategy`, and — on disarm or connection loss — stops recording and writes `telemetry.json`/`metadata.json`/`metadata.csv`. A failed photo capture never aborts the flight.

## Recording
Started/stopped by `MissionRunner` per session via `services/recording_service.py` (gated by `RECORDING_ENABLED`); output is `video.mp4` inside that session's storage folder, alongside per-waypoint photos and thumbnails.
