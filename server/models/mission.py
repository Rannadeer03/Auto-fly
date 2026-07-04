"""Pydantic models for mission data."""
from typing import Optional
from pydantic import BaseModel


class WaypointItem(BaseModel):
    """A single MAVLink mission item, format-agnostic."""

    index: int
    current: bool
    frame: int
    command: int
    param1: float
    param2: float
    param3: float
    param4: float
    latitude: float
    longitude: float
    altitude: float
    autocontinue: bool
    # True for survey waypoints that must trigger a photo capture. Set by
    # grid_planner in "hover" capture mode (param1 also carries the hold
    # time, honoured natively by ArduCopter for MAV_CMD_NAV_WAYPOINT).
    is_capture_point: bool = False


class Mission(BaseModel):
    """Canonical mission object returned by all parsers.

    Both QGC .waypoints and .plan files are normalised into this model
    before anything else in the system sees them.
    """

    filename: str
    source_format: str          # "waypoints" | "plan"
    waypoint_count: int
    nav_waypoints: int
    total_distance_m: float
    total_distance_km: float
    estimated_duration_minutes: float
    estimated_battery_percent: float
    min_altitude_m: float
    max_altitude_m: float
    waypoints: list[WaypointItem]


# Backward-compatibility alias — existing code that references MissionInfo continues to work.
MissionInfo = Mission


class MissionStatus(BaseModel):
    """Real-time mission execution status."""

    uploaded: bool = False
    waypoint_count: int = 0
    current_waypoint: int = 0
    total_waypoints: int = 0
    progress_percent: float = 0.0
    mission_info: Optional[Mission] = None


class ApiResponse(BaseModel):
    """Uniform API response envelope."""

    success: bool
    message: str
    data: Optional[dict] = None


class UploadResponse(BaseModel):
    """Response returned after a mission file upload."""

    success: bool
    message: str
    mission_info: Optional[Mission] = None
    uploaded_to_drone: bool = False
    verified: bool = False
    verification_message: str = ""
