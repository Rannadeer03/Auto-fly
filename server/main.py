"""
DronAI unified Raspberry Pi drone server — FastAPI application entry point.

Combines the Autoflight mission-control backend (Pixhawk/MAVLink) with the
Webcam camera backend (USB capture, WebRTC streaming) and adds mission
automation (auto recording, waypoint photos, telemetry logging, per-mission
storage folders).

Start with:
    cd server
    uvicorn main:app --host 0.0.0.0 --port 8000
"""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api import camera, commands, connect, mission, missions, telemetry
from config import BASE_DIR, settings
from services.log_service import log_service

logger = logging.getLogger(__name__)


# ── Drone auto-connect ─────────────────────────────────────────────────────────

def _auto_connect_loop(stop_event: threading.Event) -> None:
    """Keep trying to connect to the Pixhawk until it succeeds or we shut down.

    Uses the same ConnectionService as POST /connect, so manual API connects
    and auto-connect can never race into a double connection.
    """
    from mavlink.connection import drone_state
    from services.connection_service import connection_service

    while not stop_event.is_set():
        if drone_state.connected:
            stop_event.wait(settings.DRONE_AUTO_CONNECT_RETRY_S)
            continue
        try:
            port = connection_service.connect()
            logger.info("Auto-connect: Pixhawk connected on %s.", port)
        except RuntimeError:
            pass  # already connected via the API — nothing to do
        except Exception as exc:
            logger.info(
                "Auto-connect: Pixhawk not available (%s). Retrying in %.0fs.",
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

    # Pixhawk auto-connect (background, non-blocking, keeps retrying).
    auto_connect_stop = threading.Event()
    if settings.DRONE_AUTO_CONNECT:
        threading.Thread(
            target=_auto_connect_loop,
            args=(auto_connect_stop,),
            name="pixhawk-auto-connect",
            daemon=True,
        ).start()

    yield

    logger.info("DronAI server shutting down.")
    auto_connect_stop.set()

    # End any active mission session cleanly (stops recording, writes files).
    from services.mission_runner import mission_runner
    if mission_runner.is_active:
        mission_runner.stop_session("server shutdown")

    from services.recording_service import recording_service
    recording_service.stop()

    from services.streaming_service import streaming_service
    await streaming_service.shutdown()

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
    description="Unified Raspberry Pi drone server: mission control, camera, "
                "live streaming, and mission automation.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(connect.router)
app.include_router(mission.router)
app.include_router(telemetry.router)
app.include_router(commands.router)
app.include_router(camera.router)
app.include_router(missions.router)

# ── Core routes ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/stream", response_class=HTMLResponse)
async def stream_page():
    return FileResponse(BASE_DIR / "static" / "stream.html")


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
