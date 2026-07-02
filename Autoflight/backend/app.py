"""
Mission Planner — FastAPI application entry point.

Start with:
    cd backend
    uvicorn app:app --host 0.0.0.0 --port 8000 --reload
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from api import commands, connect, mission, telemetry
from config import BASE_DIR, settings
from services.log_service import log_service

logger = logging.getLogger(__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log_service.configure()
    logger.info(
        "Mission Planner v1.0 starting on %s:%d",
        settings.HOST, settings.PORT,
    )
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
    yield
    # Graceful shutdown — disconnect if still connected
    from mavlink.connection import drone_state, connection
    if drone_state.connected:
        logger.info("Shutting down — disconnecting from Pixhawk.")
        connection.disconnect()
    logger.info("Mission Planner stopped.")


# ── Application ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Mission Planner",
    version="1.0.0",
    description="Agricultural drone mission control interface.",
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

# ── Core routes ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health():
    from mavlink.connection import drone_state
    return {
        "status": "ok",
        "version": "1.0.0",
        "drone_connected": drone_state.connected,
        "mavlink_port": settings.MAVLINK_PORT,
    }


@app.get("/logs")
async def get_logs(count: int = 200):
    """Return recent application log entries for the web UI."""
    return {"logs": log_service.get_recent_logs(count)}


@app.delete("/logs")
async def clear_logs():
    log_service.clear_logs()
    return {"status": "cleared"}
