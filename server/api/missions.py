"""API routes for mission planning, stored mission data, and the active
mission automation session."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config import settings
from mavlink.connection import drone_state
from mavlink.mission_upload import MissionUploadError
from models.mission import UploadResponse
from services.grid_planner import GridParams, GridPlanError, generate_grid_mission
from services.mission_runner import mission_runner
from services.mission_service import mission_service
from services.storage_service import storage_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["missions"])


# ── Mission planning ───────────────────────────────────────────────────────────

class GridRequest(BaseModel):
    """Survey grid generation request from the mapping frontend."""

    polygon: list[list[float]] = Field(..., description="[[lat, lon], ...] — 3+ vertices")
    altitude_m: float = Field(default_factory=lambda: settings.DEFAULT_ALTITUDE_M)
    speed_ms: float = Field(default_factory=lambda: settings.DEFAULT_SPEED_MS)
    side_overlap_pct: float = Field(default_factory=lambda: settings.DEFAULT_SIDE_OVERLAP_PCT)
    front_overlap_pct: float = Field(default_factory=lambda: settings.DEFAULT_FRONT_OVERLAP_PCT)
    angle_deg: float = Field(default_factory=lambda: settings.DEFAULT_GRID_ANGLE_DEG)
    upload: bool = Field(True, description="Upload to the Pixhawk if connected")
    # Explicit camera interval override; when omitted, the photo spacing
    # derived from the front overlap is applied to the mission capture.
    photo_distance_m: Optional[float] = Field(None, gt=0)


class GridResponse(UploadResponse):
    plan_info: Optional[dict] = None


@router.post("/mission/generate", response_model=GridResponse)
async def generate_mission(body: GridRequest) -> GridResponse:
    """Generate a lawnmower survey mission from a polygon and upload it."""
    try:
        polygon = [(float(p[0]), float(p[1])) for p in body.polygon]
        params = GridParams(
            altitude_m=body.altitude_m,
            speed_ms=body.speed_ms,
            side_overlap_pct=body.side_overlap_pct,
            front_overlap_pct=body.front_overlap_pct,
            angle_deg=body.angle_deg,
        )
        home = None
        if drone_state.connected and (drone_state.latitude or drone_state.longitude):
            home = (drone_state.latitude, drone_state.longitude)
        mission, plan_info = generate_grid_mission(polygon, params, home=home)
    except GridPlanError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (ValueError, TypeError, IndexError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid polygon data: {exc}")

    # Apply the mapping capture interval to the mission runner: explicit
    # override wins, otherwise the overlap-derived photo spacing is used.
    applied_distance = float(body.photo_distance_m or plan_info["photo_spacing_m"])
    settings.PHOTO_CAPTURE_MODE = "distance"
    settings.PHOTO_DISTANCE_M = applied_distance
    plan_info["applied_photo_distance_m"] = round(applied_distance, 2)
    logger.info("Mission photo capture set to every %.1f m.", applied_distance)

    uploaded = False
    verified = False
    verify_msg = ""
    try:
        if body.upload:
            result = mission_service.load_generated(mission)
            uploaded = result["uploaded_to_drone"]
            verified = result["verified"]
            verify_msg = result["verification_message"]
        else:
            mission_service.store_mission(mission)
    except MissionUploadError as exc:
        logger.error("Grid mission upload failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"MAVLink upload error: {exc}")

    if uploaded and verified:
        msg = "Survey mission generated, uploaded, and verified on vehicle."
    elif uploaded:
        msg = f"Survey mission uploaded but verification failed: {verify_msg}"
    else:
        msg = "Survey mission generated. Connect to drone to upload."

    return GridResponse(
        success=True,
        message=msg,
        mission_info=mission,
        uploaded_to_drone=uploaded,
        verified=verified,
        verification_message=verify_msg,
        plan_info=plan_info,
    )


@router.get("/config")
async def get_planning_config() -> dict:
    """Configuration defaults the frontend needs for mission planning."""
    return {
        "altitude_m": settings.DEFAULT_ALTITUDE_M,
        "speed_ms": settings.DEFAULT_SPEED_MS,
        "side_overlap_pct": settings.DEFAULT_SIDE_OVERLAP_PCT,
        "front_overlap_pct": settings.DEFAULT_FRONT_OVERLAP_PCT,
        "grid_angle_deg": settings.DEFAULT_GRID_ANGLE_DEG,
        "photo_capture_mode": settings.PHOTO_CAPTURE_MODE,
        "photo_distance_m": settings.PHOTO_DISTANCE_M,
        "photo_interval_s": settings.PHOTO_INTERVAL_S,
        "recording_enabled": settings.RECORDING_ENABLED,
        "camera_hfov_deg": settings.CAMERA_HFOV_DEG,
        "camera_vfov_deg": settings.CAMERA_VFOV_DEG,
    }


# ── Mission history / results ──────────────────────────────────────────────────

@router.get("/missions")
async def list_missions() -> dict:
    """List every stored mission folder (video/photos/telemetry), newest first."""
    missions = storage_service.list_missions()
    return {"missions": missions, "count": len(missions)}


@router.get("/missions/{name}")
async def mission_detail(name: str) -> dict:
    """Full detail for one stored mission: metadata, geotagged photo index, plan."""
    detail = storage_service.get_mission_detail(name)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Mission '{name}' not found.")
    return detail


@router.get("/mission/session")
async def mission_session() -> dict:
    """Status of the active mission automation session (recording, photos)."""
    return mission_runner.get_status()
