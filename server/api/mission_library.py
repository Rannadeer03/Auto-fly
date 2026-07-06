"""API routes for the Mission Library — saved, reusable pre-flight mission
plans (as opposed to api/missions.py's post-flight session archives)."""
import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from pydantic import TypeAdapter

from config import settings
from mavlink.connection import drone_state
from mavlink.mission_upload import MissionUploadError
from models.manual_mission import ManualItemInput, to_builder_item
from models.mission import Mission
from parser.plan_writer import mission_to_plan_bytes
from services.grid_planner import GridParams, GridPlanError, generate_grid_mission
from services.manual_mission_builder import ManualMissionError, TakeoffItemData, build_manual_mission
from services.mission_library_service import mission_library_service
from services.mission_service import mission_service

_manual_item_adapter: TypeAdapter = TypeAdapter(ManualItemInput)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["mission-library"])


class SaveLibraryRequest(BaseModel):
    """Save the current drawn survey as a reusable library entry.

    Mirrors GridRequest — the mission is regenerated server-side from the
    polygon and parameters (never trusted pre-built from the client), the
    same way POST /mission/generate works.
    """

    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field("", max_length=2000)
    polygon: list[list[float]] = Field(..., description="[[lat, lon], ...] — 3+ vertices")
    altitude_m: float = Field(default_factory=lambda: settings.DEFAULT_ALTITUDE_M)
    speed_ms: float = Field(default_factory=lambda: settings.DEFAULT_SPEED_MS)
    side_overlap_pct: float = Field(default_factory=lambda: settings.DEFAULT_SIDE_OVERLAP_PCT)
    front_overlap_pct: float = Field(default_factory=lambda: settings.DEFAULT_FRONT_OVERLAP_PCT)
    angle_deg: float = Field(default_factory=lambda: settings.DEFAULT_GRID_ANGLE_DEG)
    capture_mode: Optional[str] = Field(None, pattern="^(hover|continuous)$")
    hold_time_s: Optional[float] = Field(None, ge=0, le=30)
    camera_angle_deg: Optional[float] = Field(None, ge=-90, le=0)


class ManualSaveLibraryRequest(BaseModel):
    """Save the current manual mission (home + ordered item list) as a
    reusable library entry. Mirrors ManualMissionRequest (api/missions.py)
    — the mission is (re)built server-side, never trusted pre-built from
    the client."""

    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field("", max_length=2000)
    home: list[float] = Field(..., min_length=2, max_length=2, description="[lat, lon]")
    items: list[ManualItemInput] = Field(..., min_length=1, description="in order — never reordered")
    speed_ms: float = Field(default_factory=lambda: settings.DEFAULT_SPEED_MS)


class RenameLibraryRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)


class DuplicateLibraryRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)


def _regenerate(polygon_raw: list, params_raw: dict, name: str) -> tuple[Mission, dict]:
    """Regenerate a Mission from a polygon + flight params using the current
    drone position as the launch/home point (or the polygon centroid if not
    connected). Always called fresh — at save time and again at deploy time
    — so a plan saved while disconnected is re-anchored to wherever the
    drone actually is by the time it's flown, instead of replaying a stale
    takeoff position baked in at save time."""
    try:
        polygon = [(float(p[0]), float(p[1])) for p in polygon_raw]
        params = GridParams(
            altitude_m=params_raw["altitude_m"],
            speed_ms=params_raw["speed_ms"],
            side_overlap_pct=params_raw["side_overlap_pct"],
            front_overlap_pct=params_raw["front_overlap_pct"],
            angle_deg=params_raw["angle_deg"],
        )
        home = None
        if drone_state.connected and (drone_state.latitude or drone_state.longitude):
            home = (drone_state.latitude, drone_state.longitude)
        safe_name = re.sub(r"[^\w\-]", "_", name.strip())[:120]
        return generate_grid_mission(polygon, params, home=home, mission_name=safe_name)
    except GridPlanError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid polygon/params data: {exc}")


def _migrate_legacy_manual_record(record: dict) -> dict:
    """Phase 1 saved manual entries as {launch, home, manual_waypoints} —
    Phase 2A collapses "launch" into manual_items[0] (a takeoff-type item).
    Synthesize the new shape in memory for any entry saved under the old
    one, so it keeps working instead of just breaking on deploy/detail."""
    if "manual_items" in record or "manual_waypoints" not in record:
        return record
    legacy_waypoints = record.get("manual_waypoints") or []
    launch = record.get("launch") or record.get("home") or [0.0, 0.0]
    first_altitude = legacy_waypoints[0]["altitude_m"] if legacy_waypoints else settings.DEFAULT_ALTITUDE_M
    items = [{"type": "takeoff", "lat": launch[0], "lon": launch[1], "altitude_m": first_altitude}]
    items += [
        {"type": "waypoint", "lat": w["lat"], "lon": w["lon"], "altitude_m": w["altitude_m"]}
        for w in legacy_waypoints
    ]
    return {**record, "manual_items": items}


def _regenerate_manual(
    home_raw: list, items, speed_ms: float, name: str, *, reanchor_takeoff: bool = False
) -> tuple[Mission, None]:
    """Manual-mission counterpart to _regenerate() — builds fresh from the
    given home + ordered item list (already-validated ManualItemInput
    instances, from either a live request body or a stored record replayed
    through _manual_item_adapter). When reanchor_takeoff is set (redeploy
    only), the Takeoff item's position is moved to the drone's current
    location when connected — same principle as the survey path:
    redeploying a plan saved while disconnected shouldn't replay a stale
    takeoff spot. Item order is preserved exactly as given.
    """
    try:
        home = (float(home_raw[0]), float(home_raw[1]))
        built_items = [to_builder_item(item) for item in items]
        if reanchor_takeoff and drone_state.connected and (drone_state.latitude or drone_state.longitude):
            for item in built_items:
                if isinstance(item, TakeoffItemData):
                    item.latitude = float(drone_state.latitude)
                    item.longitude = float(drone_state.longitude)
                    break
        safe_name = re.sub(r"[^\w\-]", "_", name.strip())[:120]
        return build_manual_mission(home, built_items, speed_ms, mission_name=safe_name)
    except ManualMissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (ValueError, TypeError, IndexError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid manual mission data: {exc}")


@router.post("/mission-library")
async def save_to_library(body: SaveLibraryRequest) -> dict:
    """Generate a survey from the given polygon/params and save it as a
    reusable library entry (does not touch the vehicle)."""
    params_raw = {
        "altitude_m": body.altitude_m,
        "speed_ms": body.speed_ms,
        "side_overlap_pct": body.side_overlap_pct,
        "front_overlap_pct": body.front_overlap_pct,
        "angle_deg": body.angle_deg,
    }
    mission, plan_info = _regenerate(body.polygon, params_raw, body.name)
    params = {
        **params_raw,
        "capture_mode": body.capture_mode or settings.CAPTURE_STRATEGY,
        "hold_time_s": body.hold_time_s if body.hold_time_s is not None else settings.HOVER_HOLD_TIME_S,
        "camera_angle_deg": body.camera_angle_deg if body.camera_angle_deg is not None else settings.CAMERA_PITCH_DEG,
    }
    record = mission_library_service.save(
        name=body.name, description=body.description, mission=mission, plan_info=plan_info,
        mode="survey", polygon=body.polygon, params=params,
    )
    return {"success": True, "message": f"Saved '{record['name']}' to the mission library.", "entry": record}


@router.post("/mission-library/manual")
async def save_manual_to_library(body: ManualSaveLibraryRequest) -> dict:
    """Build a manual mission from the given home + ordered item list and
    save it as a reusable library entry (does not touch the vehicle)."""
    mission, plan_info = _regenerate_manual(body.home, body.items, body.speed_ms, body.name)
    items_raw = [item.model_dump() for item in body.items]
    record = mission_library_service.save(
        name=body.name, description=body.description, mission=mission, plan_info=plan_info,
        mode="manual", home=tuple(body.home),
        manual_items=items_raw, params={"speed_ms": body.speed_ms},
    )
    return {"success": True, "message": f"Saved '{record['name']}' to the mission library.", "entry": record}


@router.get("/mission-library")
async def list_library(q: str = "") -> dict:
    entries = mission_library_service.list(q)
    return {"entries": entries, "count": len(entries), "query": q}


@router.get("/mission-library/{entry_id}")
async def library_detail(entry_id: str) -> dict:
    record = mission_library_service.get_detail(entry_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Library entry '{entry_id}' not found.")
    return _migrate_legacy_manual_record(record)


@router.patch("/mission-library/{entry_id}")
async def rename_library_entry(entry_id: str, body: RenameLibraryRequest) -> dict:
    record = mission_library_service.update(entry_id, body.name, body.description)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Library entry '{entry_id}' not found.")
    return record


@router.post("/mission-library/{entry_id}/duplicate")
async def duplicate_library_entry(entry_id: str, body: DuplicateLibraryRequest) -> dict:
    record = mission_library_service.duplicate(entry_id, body.name)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Library entry '{entry_id}' not found.")
    return record


@router.delete("/mission-library/{entry_id}")
async def delete_library_entry(entry_id: str) -> dict:
    if not mission_library_service.delete(entry_id):
        raise HTTPException(status_code=404, detail=f"Library entry '{entry_id}' not found.")
    return {"success": True, "message": f"Library entry '{entry_id}' deleted.", "id": entry_id}


@router.get("/mission-library/{entry_id}/download")
async def download_library_entry(entry_id: str) -> Response:
    """Export the saved mission as a QGroundControl-compatible .plan file."""
    record = mission_library_service.get(entry_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Library entry '{entry_id}' not found.")
    mission = Mission(**record["mission"])
    cruise_speed = float((record.get("params") or {}).get("speed_ms", 5.0))
    data = mission_to_plan_bytes(mission, cruise_speed_ms=cruise_speed)
    filename = re.sub(r"[^\w\-]", "_", record["name"])[:120] or entry_id
    return Response(
        content=data,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}.plan"'},
    )


@router.post("/mission-library/{entry_id}/deploy")
async def deploy_library_entry(entry_id: str) -> dict:
    """Upload (and verify) a saved mission to the currently connected drone.

    The mission is regenerated from the entry's stored polygon/params right
    now — not replayed from the waypoints frozen at save time — so the
    takeoff/launch position always reflects the drone's *current* location
    (or the polygon centroid if still disconnected), the same guarantee a
    fresh survey gets. Mission verification is advisory only — see
    mission_service.load_generated — a failed verification never prevents
    the upload from being reported as usable; it's surfaced to the operator
    alongside the result.
    """
    record = mission_library_service.get(entry_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Library entry '{entry_id}' not found.")
    record = _migrate_legacy_manual_record(record)

    mode = record.get("mode", "survey")
    if mode == "manual":
        raw_items = [_manual_item_adapter.validate_python(raw) for raw in record["manual_items"]]
        mission, plan_info = _regenerate_manual(
            record["home"], raw_items,
            (record.get("params") or {}).get("speed_ms", settings.DEFAULT_SPEED_MS),
            record["name"], reanchor_takeoff=True,
        )
        enrich = False
    else:
        mission, plan_info = _regenerate(record["polygon"], record["params"], record["name"])
        enrich = True

    try:
        result = mission_service.load_generated(mission, enrich=enrich)
    except MissionUploadError as exc:
        logger.error("Mission library deploy failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"MAVLink upload error: {exc}")

    uploaded = result["uploaded_to_drone"]
    verified = result["verified"]
    verify_msg = result["verification_message"]
    if uploaded and verified:
        msg = f"'{record['name']}' uploaded and verified on vehicle."
    elif uploaded:
        msg = f"'{record['name']}' uploaded but verification failed: {verify_msg}"
    else:
        msg = f"'{record['name']}' loaded. Connect to drone to upload."

    return {
        "success": True,
        "message": msg,
        "mission_info": (mission_service.current_mission or mission).model_dump(),
        "uploaded_to_drone": uploaded,
        "verified": verified,
        "verification_message": verify_msg,
        "plan_info": plan_info,
        "mode": mode,
        "polygon": record.get("polygon"),
        "params": record.get("params"),
        "home": record.get("home"),
        "manual_items": record.get("manual_items"),
    }
