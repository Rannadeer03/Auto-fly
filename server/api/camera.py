"""API routes for the camera subsystem: status, photo capture, and recording.

The camera serves autonomous missions only — there is no live streaming.
"""
import logging
from datetime import datetime

from fastapi import APIRouter

from config import settings
from models.mission import ApiResponse
from services.camera_service import camera_service, list_camera_devices
from services.recording_service import recording_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["camera"])

# Manual (non-mission) captures land here, out of the way of mission folders.
_CAPTURES_DIR = settings.MISSIONS_DIR / "captures"


@router.get("/camera/status")
async def camera_status() -> dict:
    stats = camera_service.get_stats()
    return {
        "camera": {
            "healthy": stats.healthy,
            "frozen": stats.frozen,
            "device": stats.device,
            "available_devices": list_camera_devices(),
            "measured_fps": stats.measured_fps,
            "frame_count": stats.frame_count,
            "configured_width": stats.configured_width,
            "configured_height": stats.configured_height,
            "configured_fps": stats.configured_fps,
            "last_frame_age_seconds": stats.last_frame_age_seconds,
        },
        "recording": recording_service.get_status(),
    }


@router.get("/camera/capabilities")
async def camera_capabilities() -> dict:
    return camera_service.get_capabilities()


@router.post("/camera/photo", response_model=ApiResponse)
async def capture_photo() -> ApiResponse:
    path = _CAPTURES_DIR / f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    if not camera_service.capture_photo(path):
        return ApiResponse(
            success=False,
            message="Photo capture failed — no camera frame available.",
        )
    return ApiResponse(success=True, message="Photo captured.", data={"path": str(path)})


@router.post("/camera/recording/start", response_model=ApiResponse)
async def start_recording() -> ApiResponse:
    path = _CAPTURES_DIR / f"recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
    if not recording_service.start(path):
        return ApiResponse(success=False, message="Recording already in progress.")
    return ApiResponse(success=True, message="Recording started.", data={"path": str(path)})


@router.post("/camera/recording/stop", response_model=ApiResponse)
async def stop_recording() -> ApiResponse:
    path = recording_service.stop()
    if path is None:
        return ApiResponse(success=False, message="No recording in progress.")
    return ApiResponse(success=True, message="Recording stopped.", data={"path": str(path)})
