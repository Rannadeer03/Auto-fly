"""Manual mission builder.

Turns a hand-placed Launch marker, Home marker, and an ordered sequence of
waypoints (as drawn by the user, click by click) into a Mission ready for
upload — the point-to-point counterpart to services/grid_planner.py's
auto-generated lawnmower survey.

Unlike the survey grid, there is no algorithm here: waypoint order is
whatever the caller passed in, verbatim. This module's only job is to wrap
that sequence in the same MAVLink mission-item conventions used everywhere
else in the app (home reference at index 0, NAV_TAKEOFF at the real launch
position, NAV_RTL last) and compute the same summary stats.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import settings
from models.mission import Mission, WaypointItem
from parser.waypoint_parser import _path_distance_m

_CMD_NAV_WAYPOINT = 16
_CMD_NAV_RTL = 20
_CMD_NAV_TAKEOFF = 22
_CMD_DO_CHANGE_SPEED = 178

_FRAME_GLOBAL = 0
_FRAME_GLOBAL_REL = 3

_MAX_MANUAL_WAYPOINTS = 900  # same headroom as grid_planner, under the 1000-item mission limit


class ManualMissionError(ValueError):
    """Raised when a manual mission cannot be built from the given inputs."""


@dataclass
class ManualWaypoint:
    latitude: float
    longitude: float
    altitude_m: float


def _validate(
    launch: tuple[float, float],
    home: tuple[float, float],
    waypoints: list[ManualWaypoint],
    speed_ms: float,
) -> None:
    if len(waypoints) < 1:
        raise ManualMissionError("A manual mission needs at least one waypoint.")
    if len(waypoints) > _MAX_MANUAL_WAYPOINTS:
        raise ManualMissionError(
            f"{len(waypoints)} waypoints exceeds the limit ({_MAX_MANUAL_WAYPOINTS})."
        )
    if not 0.5 <= speed_ms <= 25.0:
        raise ManualMissionError("Speed must be between 0.5 and 25 m/s.")
    for wp in waypoints:
        if not 2.0 <= wp.altitude_m <= 500.0:
            raise ManualMissionError("Altitude must be between 2 and 500 m for every waypoint.")


def build_manual_mission(
    launch: tuple[float, float],
    home: tuple[float, float],
    waypoints: list[ManualWaypoint],
    speed_ms: float,
    mission_name: str | None = None,
) -> tuple[Mission, None]:
    """Build a point-to-point Mission from a manually-placed launch/home/path.

    Returns (mission, None) — the second element mirrors grid_planner's
    (mission, plan_info) return shape for API symmetry, but manual missions
    have no lawnmower-specific stats (line spacing, footprint, photo count)
    to report, so it's always None rather than a partially-populated
    PlanInfo the frontend would have to special-case.
    """
    _validate(launch, home, waypoints, speed_ms)

    built: list[WaypointItem] = []

    def add(command: int, lat: float, lon: float, alt: float,
            frame: int = _FRAME_GLOBAL_REL, current: bool = False,
            p1: float = 0.0, p2: float = 0.0) -> None:
        built.append(WaypointItem(
            index=len(built), current=current, frame=frame, command=command,
            param1=p1, param2=p2, param3=0.0, param4=0.0,
            latitude=lat, longitude=lon, altitude=alt, autocontinue=True,
        ))

    # 0: home (AMSL frame, matching parser/grid_planner convention) — a
    # reference marker only, never actually flown through.
    add(_CMD_NAV_WAYPOINT, home[0], home[1], 0.0, frame=_FRAME_GLOBAL, current=True)
    # 1: takeoff at the actual launch position, climbing to the first
    # waypoint's altitude.
    add(_CMD_NAV_TAKEOFF, launch[0], launch[1], waypoints[0].altitude_m)
    # 2: set ground speed
    add(_CMD_DO_CHANGE_SPEED, 0.0, 0.0, 0.0, p1=1.0, p2=speed_ms)
    # 3+: the user's own path, in the exact order they placed it — never
    # sorted, never reversed.
    for wp in waypoints:
        add(_CMD_NAV_WAYPOINT, wp.latitude, wp.longitude, wp.altitude_m)
    # final: RTL — ArduPilot returns to the vehicle's true arm-location home
    # regardless of what the index-0 item above says.
    add(_CMD_NAV_RTL, 0.0, 0.0, 0.0)

    nav_points = [
        w for w in built
        if w.command == _CMD_NAV_WAYPOINT and not w.current
        and (w.latitude != 0 or w.longitude != 0)
    ]
    total_m = _path_distance_m(nav_points)
    duration_s = total_m / max(speed_ms, 0.1)
    consumed_mah = (duration_s / 3600.0) * settings.CRUISE_CURRENT_AMPS * 1000.0
    battery_pct = min((consumed_mah / settings.DEFAULT_BATTERY_CAPACITY_MAH) * 100.0, 100.0)
    altitudes = [wp.altitude_m for wp in waypoints]

    mission = Mission(
        filename=f"{mission_name}.plan" if mission_name else "manual_mission.plan",
        source_format="manual",
        waypoint_count=len(built),
        nav_waypoints=len(nav_points),
        total_distance_m=round(total_m, 1),
        total_distance_km=round(total_m / 1000.0, 3),
        estimated_duration_minutes=round(duration_s / 60.0, 1),
        estimated_battery_percent=round(battery_pct, 1),
        min_altitude_m=min(altitudes),
        max_altitude_m=max(altitudes),
        waypoints=built,
    )

    return mission, None
