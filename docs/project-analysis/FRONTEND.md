# FRONTEND

Vayuraksha Mission Planner — React 19 + TypeScript + Vite 8 + Tailwind v4, feature-based (`src/features/*`), MapLibre GL for mapping.

## Pages (`web/src/pages/`)
| Page | Sidebar section | Purpose |
|---|---|---|
| `mission-page.tsx` | `mission` / `survey-settings` | The map surface; Survey or Manual planner, kept permanently mounted |
| `telemetry-page.tsx` | `telemetry` | Live GPS/battery/attitude/link telemetry |
| `drone-status-page.tsx` | `drone-status` | Serial port + sensor/link health |
| `camera-page.tsx` | `camera` | Camera status, manual photo/recording controls |
| `mission-library-page.tsx` | `mission-library` | Saved, reusable mission plans |
| `mission-files-page.tsx` | `mission-files` | Mission History: list + detail (replay map, images, log, ZIP) |
| `logs-page.tsx` | `logs` | Live app log tail |
| `settings-page.tsx` | `settings` | Server planning defaults |

## Routing
No client-side path routing (React Router, etc.). `App.tsx` renders based on `useUiStore().activeSection` (a Zustand-persisted enum); this keeps `/` as the only URL route so it never collides with backend JSON routes served from the same origin (e.g. `GET /missions`). `MissionPage` is always mounted (visibility toggled via CSS) so the MapLibre GL context/drawn boundary survives navigation; every other page is `React.lazy` + `Suspense`.

## Mission Planner
`mission-page.tsx` hosts both modes on one `<MissionMap>`, toggled by `MissionModeToggle` (`useUiStore().missionMode`); switching modes resets the other mode's draft (`useMissionDraftStore().reset()`).

### Survey Mode (`features/survey/`, `features/map/`)
- `farm-draw-tool.tsx` — draw the farm polygon (Terra Draw)
- `use-auto-generate-survey.ts` — regenerates the grid live from `POST /mission/generate` on every parameter change
- `flight-parameters-panel.tsx` — altitude, speed, overlaps, grid angle, capture mode
- `live-estimation-panel.tsx`, `waypoint-detail-card.tsx`, `survey-layer.tsx`, `mission-anchors.tsx`

### Manual Mode (`features/manual-mission/`)
- `manual-mission-tool.tsx` / `manual-mission-layer.tsx` — click-to-place Takeoff/Waypoint/Loiter/RTL/Land items on the map
- `mission-inspector.tsx` — item list/edit panel
- `non-positional-items-chips.tsx` — non-map items (e.g. Change Speed)
- `mission-settings-panel.tsx` — mission-level settings (Change Speed/Trigger Distance persisted but not yet sent to vehicle)
- `use-generate-manual-mission.ts` — calls `POST /mission/generate-manual`
- `use-upload-manual-mission.ts`
- `drag-suppression.ts` — map-drag/click disambiguation helper

Shared execution UI regardless of mode: `features/mission-execution/` (`upload-mission-bar.tsx`, `command-bar.tsx`, `use-upload-mission.ts`, `use-flight-commands.ts` for ARM/START/PAUSE/RESUME/RTL/LAND/emergency-stop).

## Mission Library
`features/mission-library/` + `mission-library-page.tsx` + `mission-library-service.ts`: save/list/rename/duplicate/delete/download/re-deploy saved plans (both Survey and Manual). Backed by `GET/POST/PATCH/DELETE /mission-library*`.

## Mission History
`features/mission-history/`: `mission-list.tsx`, `mission-detail-panel.tsx`, `mission-replay-map.tsx`, `use-missions.ts`. Rendered by `mission-files-page.tsx` (nav label "Mission Files"). Backed by `GET /missions`, `/missions/{name}`, `/missions/{name}/log`, `/missions/{name}/download`, `DELETE /missions/{name}`.

## Dashboard
No single dashboard page; status is distributed — `TopStatusBar` + `StatusBanner` (always visible, `components/layout/`), plus dedicated Telemetry/Drone-Status/Camera pages and `features/telemetry/components/health-grid.tsx` + `attitude-indicator.tsx`.

## Stores (`web/src/store/`, Zustand)
- `ui-store.ts` — active sidebar section, sidebar collapsed state, base layer, mission mode, current selection (survey waypoint index vs. manual item id) — persisted
- `mission-draft-store.ts` — in-progress draft mission state (farm polygon / manual items), reset on mode switch
- `geolocation-store.ts` — "My Location" tracking (requires secure context — see HTTPS note in server docs)

## API Layer (`web/src/services/`)
`api-client.ts` (base fetch wrapper, `VITE_API_BASE_URL` override) + `query-client.ts` (TanStack Query) fronting one service module per backend domain: `mission-service`, `mission-history-service`, `mission-library-service`, `telemetry-service`, `camera-service`, `connection-service`, `command-service`, `logs-service`.

## Major Components
`components/layout/` (`sidebar.tsx`, `top-status-bar.tsx`), `components/feedback/` (`status-banner.tsx`, `error-boundary.tsx`), `components/ui/` (10 Radix-based primitives: dialog, select, slider, switch, tooltip, panel, etc.), `features/map/components/mission-map.tsx` (MapLibre GL context provider — `map-context.tsx` propagates only to React descendants, which shapes where floating chrome can live).
