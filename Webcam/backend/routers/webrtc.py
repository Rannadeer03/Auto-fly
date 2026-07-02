"""HTTP/signaling surface for the WebRTC subsystem.

Kept deliberately thin: this router only does request/response plumbing. All
state and lifecycle logic lives in `services/webrtc_manager.py` and
`services/camera.py`, reached here via FastAPI dependencies on `app.state`.
That separation is what lets future routers (`/telemetry`, `/mission`,
`/mapping`) share the same `Camera`/`WebRTCManager` instances without
importing this module.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.config import BACKEND_DIR
from backend.services.camera import Camera
from backend.services.webrtc_manager import WebRTCManager
from backend.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()

_STATIC_DIR = BACKEND_DIR / "static"


class OfferRequest(BaseModel):
    sdp: str
    type: str


class AnswerResponse(BaseModel):
    sdp: str
    type: str


def get_camera(request: Request) -> Camera:
    return request.app.state.camera


def get_webrtc_manager(request: Request) -> WebRTCManager:
    return request.app.state.webrtc_manager


@router.get("/")
async def index() -> FileResponse:
    return FileResponse(_STATIC_DIR / "index.html")


@router.get("/health")
async def health(request: Request) -> dict:
    camera: Camera = get_camera(request)
    healthy = camera.is_healthy
    return {
        "status": "ok" if healthy else "degraded",
        "camera_healthy": healthy,
    }


@router.get("/api/status")
async def status(request: Request) -> dict:
    camera: Camera = get_camera(request)
    manager: WebRTCManager = get_webrtc_manager(request)

    stats = camera.get_stats()
    return {
        "camera": {
            "healthy": stats.healthy,
            "measured_fps": stats.measured_fps,
            "frame_count": stats.frame_count,
            "configured_width": stats.configured_width,
            "configured_height": stats.configured_height,
            "configured_fps": stats.configured_fps,
            "last_frame_age_seconds": stats.last_frame_age_seconds,
        },
        "webrtc": manager.get_status(),
    }


@router.post("/offer", response_model=AnswerResponse)
async def offer(request: Request, body: OfferRequest) -> AnswerResponse:
    manager: WebRTCManager = get_webrtc_manager(request)
    answer = await manager.create_peer_connection(sdp=body.sdp, type_=body.type)
    return AnswerResponse(sdp=answer.sdp, type=answer.type)
