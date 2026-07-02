"""FastAPI application entry point.

Why a `lifespan` context manager instead of `@app.on_event`: it's the
non-deprecated FastAPI mechanism, and critically it gives us a single place
that guarantees symmetric startup/shutdown — the camera thread and every
peer connection opened during the process's life are guaranteed a matching
stop/close call, which is what "no leaked VideoCapture / no leaked
RTCPeerConnection" requires in practice.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.config import BACKEND_DIR, load_config
from backend.routers import webrtc
from backend.services.camera import Camera
from backend.services.webrtc_manager import WebRTCManager
from backend.utils.logger import get_logger, setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    config = load_config()
    setup_logging(config.log_dir)
    logger = get_logger(__name__)

    logger.info("DronAI WebRTC backend starting up")

    camera = Camera(config.camera)
    camera.start()

    webrtc_manager = WebRTCManager(camera, config.camera)

    app.state.config = config
    app.state.camera = camera
    app.state.webrtc_manager = webrtc_manager

    try:
        yield
    finally:
        logger.info("DronAI WebRTC backend shutting down")
        await webrtc_manager.shutdown()
        camera.stop()
        logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(title="DronAI WebRTC Backend", lifespan=lifespan)

    app.include_router(webrtc.router)
    app.mount(
        "/static",
        StaticFiles(directory=BACKEND_DIR / "static"),
        name="static",
    )

    return app


app = create_app()
