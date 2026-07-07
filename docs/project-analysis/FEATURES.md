# FEATURES

## Completed
- Survey Mode: farm-polygon draw → live lawnmower grid generation, flight-parameter panel, live time/battery estimation
- Manual Mode: click-to-place Takeoff/Waypoint/Loiter/RTL/Land, mission inspector, non-positional item chips, generate + upload
- MAVLink mission upload/verify/clear/download (full GCS handshake, read-back verification)
- Mission Library: save/list/rename/duplicate/delete/download/re-deploy for both Survey and Manual plans
- Mission History ("Mission Files"): auto-indexed post-flight sessions, search, detail view, flight replay map, ZIP export, delete
- Hover-capture automation: position/altitude/stability-gated single photo per capture waypoint, keyed off `MAV_CMD_NAV_LOITER_TIME` completion
- GCS-independent mission watchdog — recording/capture trigger correctly even if AUTO was entered via RC switch or QGroundControl directly, not just this app's own Start button
- Video recording per mission session
- Live telemetry (GPS, battery, attitude, mode, armed, link health), Drone Status page, Camera status/manual controls
- Flight commands: ARM/DISARM/START/PAUSE/RESUME/RTL/LAND/emergency-stop, each pre-validated and with structured failure reasons
- Pixhawk auto-connect + auto-reconnect link supervisor (heartbeat-staleness detection)
- Camera auto-detect + auto-reconnect capture thread
- QGroundControl `.plan`/`.waypoints` import and export (round-trip via `plan_parser.py`/`plan_writer.py`)
- HTTPS via self-signed cert so the browser Geolocation API ("My Location") works over plain LAN access
- Centralized env-driven configuration (`server/.env`), boot-time network verification, systemd auto-start service

## Partial
- Manual Mode "Change Speed" and "Trigger Distance" items: persisted with the mission but **not yet sent to the vehicle** (per `mission-settings-panel.tsx`)
- `ContinuousCaptureStrategy` (distance/time-triggered photo capture without hovering): implemented but not wired as the default, explicitly "reserved for future use"
- Manual Mode item list is append/click-ordered only — no drag-reorder or mid-list insert yet

## Planned
- Manual Mode drag-reorder / insert-at-position ("Phase 2B+", per `web/src/store/ui-store.ts` comment on `selectedManualItemId`)
- Continuous capture mode exposed as a real, selectable option (UI already labels it "Continuous Capture (future)" and disables/reserves it)
- Higher-resolution satellite basemap via a licensed provider (MapTiler/Mapbox) — documented as a drop-in `.env` config change, not yet the default

## Missing
- No authentication/authorization on the API or SPA (LAN-only trust model, permissive CORS)
- No automated test suite beyond none found under `server/` or `web/` in this branch (no `tests/` directory present)
- No CI/CD pipeline files found in this branch

## Known Technical Debt
- `LOG_TELEMETRY_RX` debug flag in `config.py` is explicitly marked "TEMP DEBUG — remove this flag and its call sites once hardware telemetry is confirmed"
- Manual mission "settings saved but not applied" gap (see Partial) is a known, commented UI/backend mismatch, not an oversight
- Permissive `CORS allow_origins=["*"]` is appropriate for the current LAN-only deployment model but would need tightening for any non-trusted-network exposure
