"""API routes for mission planning, stored mission data, and the active
mission automation session."""
import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
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
    # Explicit camera interval override (continuous mode only); when omitted,
    # the photo spacing derived from the front overlap is applied.
    photo_distance_m: Optional[float] = Field(None, gt=0)
    # Capture strategy override — defaults to settings.CAPTURE_STRATEGY ("hover").
    capture_mode: Optional[str] = Field(None, pattern="^(hover|continuous)$")
    # Hover-mode hold time override (seconds), defaults to settings.HOVER_HOLD_TIME_S.
    hold_time_s: Optional[float] = Field(None, ge=0, le=30)
    # Display name from the flight-parameters panel; becomes the mission filename.
    mission_name: Optional[str] = Field(None, max_length=120)
    # Fixed camera mounting angle override (degrees from horizontal, -90=nadir).
    camera_angle_deg: Optional[float] = Field(None, ge=-90, le=0)


class GridResponse(UploadResponse):
    plan_info: Optional[dict] = None


@router.post("/mission/generate", response_model=GridResponse)
async def generate_mission(body: GridRequest) -> GridResponse:
    """Generate a lawnmower survey mission from a polygon and upload it."""
    # Capture-strategy overrides apply for the duration of this generation
    # (and the mission session it produces) — explicit request values win,
    # otherwise the server defaults are used.
    settings.CAPTURE_STRATEGY = body.capture_mode or settings.CAPTURE_STRATEGY
    if body.hold_time_s is not None:
        settings.HOVER_HOLD_TIME_S = body.hold_time_s
    if body.camera_angle_deg is not None:
        settings.CAMERA_PITCH_DEG = body.camera_angle_deg

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
        safe_name = (
            re.sub(r"[^\w\-]", "_", body.mission_name.strip())[:120]
            if body.mission_name and body.mission_name.strip()
            else None
        )
        mission, plan_info = generate_grid_mission(
            polygon, params, home=home, mission_name=safe_name
        )
    except GridPlanError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (ValueError, TypeError, IndexError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid polygon data: {exc}")

    if settings.CAPTURE_STRATEGY == "continuous":
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

    # Both branches above enrich the mission (densified legs + native loiter
    # items) before storing it — reflect that actual mission back to the
    # frontend instead of the pre-enrichment grid_planner output.
    mission = mission_service.current_mission or mission

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
        "capture_mode": settings.CAPTURE_STRATEGY,
        "hover_hold_time_s": settings.HOVER_HOLD_TIME_S,
        "photo_capture_mode": settings.PHOTO_CAPTURE_MODE,
        "photo_distance_m": settings.PHOTO_DISTANCE_M,
        "photo_interval_s": settings.PHOTO_INTERVAL_S,
        "recording_enabled": settings.RECORDING_ENABLED,
        "camera_hfov_deg": settings.CAMERA_HFOV_DEG,
        "camera_vfov_deg": settings.CAMERA_VFOV_DEG,
        "camera_width_px": settings.CAMERA_WIDTH,
        "camera_height_px": settings.CAMERA_HEIGHT,
        "camera_pitch_deg": settings.CAMERA_PITCH_DEG,
    }


# ── Mission history / results ──────────────────────────────────────────────────

@router.get("/missions")
async def list_missions(q: str = "") -> dict:
    """List every stored mission folder, newest first.

    Optional ?q= filters on folder name, mission name, dates and end reason.
    """
    missions = storage_service.list_missions(q)
    active_folder = None
    if mission_runner.is_active:
        active_folder = mission_runner.get_status().get("mission_folder")
    for m in missions:
        m["active"] = m["name"] == active_folder
    return {"missions": missions, "count": len(missions), "query": q}


@router.get("/missions/{name}")
async def mission_detail(name: str) -> dict:
    """Full detail for one stored mission: metadata, the full per-image
    metadata array (position, attitude, waypoint, GPS fix, etc. — see
    services/storage_service.py:IMAGE_METADATA_FIELDS), executed plan, file
    index, and telemetry-derived flight statistics."""
    detail = storage_service.get_mission_detail(name)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Mission '{name}' not found.")
    detail["active"] = _is_active_mission(name)
    return detail


@router.get("/missions/{name}/log")
async def mission_log(name: str, tail: int = 500) -> dict:
    """The mission's own log file (last *tail* lines)."""
    root = storage_service.resolve_mission_root(name)
    if root is None:
        raise HTTPException(status_code=404, detail=f"Mission '{name}' not found.")
    log_file = root / "logs" / "mission.log"
    if not log_file.exists():
        return {"name": name, "lines": [], "total_lines": 0}
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not read log: {exc}")
    return {"name": name, "lines": lines[-tail:], "total_lines": len(lines)}


@router.get("/missions/{name}/download")
async def download_mission(name: str) -> StreamingResponse:
    """Export the complete mission folder as a single ZIP archive.

    The archive is streamed straight from the mission's files on disk —
    nothing is copied or stored server-side.
    """
    root = storage_service.resolve_mission_root(name)
    if root is None:
        raise HTTPException(status_code=404, detail=f"Mission '{name}' not found.")
    if _is_active_mission(name):
        raise HTTPException(
            status_code=409,
            detail="Mission is still recording — download it after it completes.",
        )
    return StreamingResponse(
        storage_service.zip_stream(root),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}.zip"'},
    )


@router.delete("/missions/{name}")
async def delete_mission(name: str) -> dict:
    """Permanently delete a stored mission folder and everything in it."""
    if storage_service.resolve_mission_root(name) is None:
        raise HTTPException(status_code=404, detail=f"Mission '{name}' not found.")
    if _is_active_mission(name):
        raise HTTPException(
            status_code=409,
            detail="Mission is still recording — stop the session before deleting.",
        )
    if not storage_service.delete_mission(name):
        raise HTTPException(status_code=500, detail="Failed to delete mission.")
    logger.info("Mission '%s' deleted via API.", name)
    return {"success": True, "message": f"Mission '{name}' deleted.", "name": name}


def _is_active_mission(name: str) -> bool:
    return (
        mission_runner.is_active
        and mission_runner.get_status().get("mission_folder") == name
    )


@router.get("/mission/session")
async def mission_session() -> dict:
    """Status of the active mission automation session (recording, photos)."""
    return mission_runner.get_status()
