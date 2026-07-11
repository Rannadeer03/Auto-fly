// Backend base URL resolution:
//   - Production: the Vite build output is served by the same FastAPI process
//     (server/static + templates/index.html), so relative paths just work.
//   - Dev: Vite runs on :5173, backend on :8000. CORS is already permissive
//     on the backend (main.py), so we call it cross-origin directly.
//   - VITE_API_BASE_URL always wins (e.g. to point dev at a real Pi's IP).
export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? 'http://localhost:8000' : '')

// Poll intervals (ms) — kept centralized so throttling behavior is easy to audit.
export const TELEMETRY_POLL_MS = 1000
export const MISSION_SESSION_POLL_MS = 2000
export const HEALTH_POLL_MS = 4000
export const CAMERA_STATUS_POLL_MS = 5000
export const LOGS_POLL_MS = 5000
// Mission folders are written entirely server-side (mission_runner.py, driven
// by the watchdog/RC switch/QGroundControl — not by any frontend mutation),
// so the Mission Files list has no "create" event to invalidate on. Poll it
// instead so a finished flight appears without a manual page reload.
export const MISSION_LIST_POLL_MS = 5000

// Debounce for regenerating the survey after a flight-parameter edit.
export const SURVEY_REGENERATE_DEBOUNCE_MS = 350
