# Vayuraksha Mission Planner

The web-based Ground Control Station for the DronAI Raspberry Pi drone
computer (see `../server`). Draw a farm boundary, get a fully-generated
survey mission — waypoints, camera footprint, overlaps, flight time, and
battery estimate — with no QGroundControl required, then fly it and browse
the results (photos, metadata, flight replay) when it's done.

React 19 + TypeScript + Vite + Tailwind v4, feature-based architecture
(`src/features/*`), MapLibre GL for mapping.

## Development

```bash
npm install
npm run dev       # http://localhost:5173, talks to a backend on :8000
```

CORS is already permissive on the backend (`server/main.py`) for this. To
point dev at a real Pi instead of `localhost:8000`, copy `.env.example` to
`.env` and set `VITE_API_BASE_URL`.

## Production build

```bash
npm run build      # -> dist/
```

`server/main.py` serves `dist/` directly as a static SPA shell — there is
no separate frontend deployment step beyond building before (re)starting
the server (see `server/deploy/install.sh`).

## Higher-resolution satellite imagery

The default basemap (Esri World Imagery) tops out around z19 native
resolution in most regions, which is why very close zoom looks upscaled/
blurry rather than sharp — that's an imagery-provider limit, not a bug.
See `.env.example` for how to plug in a licensed higher-zoom provider
(MapTiler Satellite, Mapbox Satellite, etc.) with no code changes.

## Project layout

```
src/
  components/   shared UI primitives (button, panel, dialog, ...) and layout
  features/     one folder per domain: map, survey, telemetry,
                mission-execution, mission-history, camera
  hooks/        cross-feature React Query hooks (telemetry, health, ...)
  pages/        route-level components composed from features
  services/     typed fetch wrappers around the backend API
  store/        Zustand stores (UI state, mission draft)
  types/        TypeScript types mirroring the backend's Pydantic models
  constants/    map/tile config, MAVLink command IDs, polling intervals
  utils/        geo math, formatting, class-name helpers
```
