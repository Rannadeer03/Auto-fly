"""
DronAI unified Raspberry Pi drone server — FastAPI application entry point.

Self-contained drone computer: after power-on, systemd starts this app,
which connects to the Pixhawk over UART automatically (and reconnects if the
link drops), initialises the camera, and serves the single mission-planning
and mapping website.

Start manually with:
    cd server
    uvicorn main:app --host 0.0.0.0 --port 8000
"""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from api import camera, commands, connect, mission, missions, telemetry
from config import BASE_DIR, settings
from services.log_service import log_service

# Vite build output (cd web && npm run build). The React app never uses
# client-side path routing — all in-app navigation is state-driven, not
# URL-driven — specifically so "/" is the only page route and it can never
# collide with an API path (e.g. GET /missions) served by the same origin.
WEB_DIST = BASE_DIR.parent / "web" / "dist"

logger = logging.getLogger(__name__)


# ── Pixhawk link supervisor ────────────────────────────────────────────────────

def _link_supervisor_loop(stop_event: threading.Event) -> None:
    """Keep the single MAVLink connection alive for the life of the process.

    - Not connected  → try to connect (UART port from config).
    - Connected but heartbeat stale for LINK_STALE_S → tear down + reconnect.

    Uses the same ConnectionService as POST /connect, so manual API connects
    and the supervisor can never race into a second connection.
    """
    from mavlink.connection import drone_state
    from services.connection_service import connection_service

    while not stop_event.is_set():
        try:
            if not drone_state.connected:
                port = connection_service.connect()
                logger.info("Link supervisor: Pixhawk connected on %s.", port)
            elif drone_state.last_heartbeat_ago_s > settings.LINK_STALE_S:
                logger.warning(
                    "Link supervisor: heartbeat stale (%.1fs) — reconnecting.",
                    drone_state.last_heartbeat_ago_s,
                )
                connection_service.disconnect()
                continue  # reconnect on the next iteration without waiting
        except RuntimeError:
            pass  # already connected via the API — nothing to do
        except Exception as exc:
            logger.info(
                "Link supervisor: Pixhawk not available (%s). Retrying in %.0fs.",
                exc, settings.DRONE_AUTO_CONNECT_RETRY_S,
            )
        stop_event.wait(settings.DRONE_AUTO_CONNECT_RETRY_S)


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log_service.configure()
    logger.info("DronAI server v2.0 starting on %s:%d", settings.HOST, settings.PORT)

    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
    settings.MISSIONS_DIR.mkdir(parents=True, exist_ok=True)

    # Camera capture thread — runs for the life of the process and
    # auto-reconnects internally if the USB camera drops.
    from services.camera_service import camera_service
    camera_service.start()

    # Pixhawk connect + auto-reconnect (background, non-blocking).
    supervisor_stop = threading.Event()
    if settings.DRONE_AUTO_CONNECT:
        threading.Thread(
            target=_link_supervisor_loop,
            args=(supervisor_stop,),
            name="pixhawk-link-supervisor",
            daemon=True,
        ).start()

    yield

    logger.info("DronAI server shutting down.")
    supervisor_stop.set()

    # End any active mission session cleanly (stops recording, writes files).
    from services.mission_runner import mission_runner
    if mission_runner.is_active:
        mission_runner.stop_session("server shutdown")

    from services.recording_service import recording_service
    recording_service.stop()

    camera_service.stop()

    from mavlink.connection import drone_state, connection
    if drone_state.connected:
        logger.info("Disconnecting from Pixhawk.")
        connection.disconnect()

    logger.info("DronAI server stopped.")


# ── Application ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="DronAI Server",
    version="2.0.0",
    description="Self-contained Raspberry Pi drone computer: mission planning, "
                "mapping, camera automation, and Pixhawk control.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if (WEB_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=str(WEB_DIST / "assets")), name="frontend-assets")

# Mission outputs (photos, video, mapping data) — browsable by the frontend.
settings.MISSIONS_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/missions-data",
    StaticFiles(directory=str(settings.MISSIONS_DIR)),
    name="missions-data",
)

# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(connect.router)
app.include_router(mission.router)
app.include_router(telemetry.router)
app.include_router(commands.router)
app.include_router(camera.router)
app.include_router(missions.router)

# ── Core routes ────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def index():
    """Serve the built React SPA shell. No templating — it's a static build."""
    index_file = WEB_DIST / "index.html"
    if not index_file.is_file():
        return HTMLResponse(
            "<h1>Frontend not built</h1>"
            "<p>Run <code>cd web &amp;&amp; npm install &amp;&amp; npm run build</code>, "
            "then restart the server.</p>",
            status_code=503,
        )
    return FileResponse(index_file)


@app.get("/health")
async def health():
    from mavlink.connection import drone_state
    from services.camera_service import camera_service
    from services.mission_runner import mission_runner
    from services.recording_service import recording_service
    return {
        "status": "ok",
        "version": "2.0.0",
        "drone_connected": drone_state.connected,
        "mavlink_port": settings.MAVLINK_PORT,
        "camera_healthy": camera_service.is_healthy,
        "recording": recording_service.is_recording,
        "mission_session_active": mission_runner.is_active,
    }


@app.get("/logs")
async def get_logs(count: int = 200):
    """Return recent application log entries for the web UI."""
    return {"logs": log_service.get_recent_logs(count)}


@app.delete("/logs")
async def clear_logs():
    log_service.clear_logs()
    return {"status": "cleared"}
