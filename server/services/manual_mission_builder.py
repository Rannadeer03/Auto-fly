"""Manual mission builder.

Turns an ordered, user-assembled list of mission items — Takeoff, Waypoint,
Loiter, RTL, Land, Change Speed, and (later) more — into a Mission ready
for upload. This is the point-to-point counterpart to
services/grid_planner.py's auto-generated lawnmower survey: there is no
algorithm here, item order is whatever the caller passed in, verbatim.

Adding a new MAVLink mission item type later means adding one dataclass
here and one branch in _emit_item() — nothing else in this module (or its
caller, server/api/missions.py) needs to change structurally.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from config import settings
from models.mission import Mission, WaypointItem
from parser.waypoint_parser import _path_distance_m

_CMD_NAV_WAYPOINT = 16
_CMD_NAV_LOITER_TIME = 19
_CMD_NAV_RTL = 20
_CMD_NAV_LAND = 21
_CMD_NAV_TAKEOFF = 22
_CMD_DO_CHANGE_SPEED = 178

_FRAME_GLOBAL = 0
_FRAME_GLOBAL_REL = 3

_MAX_MANUAL_ITEMS = 900  # same headroom as grid_planner, under the 1000-item mission limit


class ManualMissionError(ValueError):
    """Raised when a manual mission cannot be built from the given inputs."""


@dataclass
class TakeoffItemData:
    latitude: float
    longitude: float
    altitude_m: float


@dataclass
class WaypointItemData:
    latitude: float
    longitude: float
    altitude_m: float


@dataclass
class LoiterItemData:
    latitude: float
    longitude: float
    altitude_m: float
    hold_time_s: float


@dataclass
class RtlItemData:
    pass


@dataclass
class LandItemData:
    latitude: float
    longitude: float


@dataclass
class ChangeSpeedItemData:
    speed_ms: float


ManualItemData = Union[
    TakeoffItemData, WaypointItemData, LoiterItemData, RtlItemData, LandItemData, ChangeSpeedItemData,
]

# Item types that describe a real flight-path *position* — used both to
# require at least one of them and to compute the flown distance. RTL and
# Change Speed have no position of their own.
_POSITIONAL_TYPES = (TakeoffItemData, WaypointItemData, LoiterItemData, LandItemData)


def _validate(items: list[ManualItemData], speed_ms: float, acceptance_radius_m: float | None) -> None:
    if not any(isinstance(it, _POSITIONAL_TYPES) for it in items):
        raise ManualMissionError("A manual mission needs at least one Takeoff or Waypoint item.")
    if len(items) > _MAX_MANUAL_ITEMS:
        raise ManualMissionError(f"{len(items)} items exceeds the limit ({_MAX_MANUAL_ITEMS}).")
    if not 0.5 <= speed_ms <= 25.0:
        raise ManualMissionError("Speed must be between 0.5 and 25 m/s.")
    if acceptance_radius_m is not None and not 0.5 <= acceptance_radius_m <= 50.0:
        raise ManualMissionError("Acceptance radius must be between 0.5 and 50 m.")
    for it in items:
        if isinstance(it, (TakeoffItemData, WaypointItemData, LoiterItemData)):
            if not 2.0 <= it.altitude_m <= 500.0:
                raise ManualMissionError("Altitude must be between 2 and 500 m for every item.")
        if isinstance(it, LoiterItemData) and not 0.0 <= it.hold_time_s <= 600.0:
            raise ManualMissionError("Loiter hold time must be between 0 and 600 s.")
        if isinstance(it, ChangeSpeedItemData) and not 0.5 <= it.speed_ms <= 25.0:
            raise ManualMissionError("Change Speed value must be between 0.5 and 25 m/s.")


def build_manual_mission(
    home: tuple[float, float],
    items: list[ManualItemData],
    speed_ms: float,
    mission_name: str | None = None,
    acceptance_radius_m: float | None = None,
) -> tuple[Mission, None]:
    """Build a Mission from a manually-assembled, ordered mission-item list.

    Returns (mission, None) — the second element mirrors grid_planner's
    (mission, plan_info) return shape for API symmetry; manual missions
    have no lawnmower-specific stats to report.

    Item order is preserved exactly as given — never sorted, never
    reversed. A DO_CHANGE_SPEED item is auto-inserted right after the first
    Takeoff (today's UI only offers one global speed value, applied at that
    fixed position) and a final NAV_RTL is auto-appended unless the caller
    already included one — both become ordinary user-placed items once the
    map UI supports inserting them anywhere.

    acceptance_radius_m (Mission Settings' "Acceptance Radius", falls back
    to config.WAYPOINT_RADIUS_M) is written into MAV_CMD_NAV_WAYPOINT/
    LOITER_TIME/LAND's param2 — the real MAVLink "how close counts as
    reached" radius — for every positioned item. This is the one Mission
    Settings value with a direct MAVLink mission-item representation;
    Takeoff/Climb/Descent/RTL/Land Speed are vehicle parameters, not mission
    items, so they aren't applied here (see models/manual_mission.py).
    """
    _validate(items, speed_ms, acceptance_radius_m)
    radius = acceptance_radius_m if acceptance_radius_m is not None else settings.WAYPOINT_RADIUS_M

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

    speed_inserted = False
    has_rtl = any(isinstance(it, RtlItemData) for it in items)

    for item in items:
        if isinstance(item, TakeoffItemData):
            add(_CMD_NAV_TAKEOFF, item.latitude, item.longitude, item.altitude_m)
            if not speed_inserted:
                add(_CMD_DO_CHANGE_SPEED, 0.0, 0.0, 0.0, p1=1.0, p2=speed_ms)
                speed_inserted = True
        elif isinstance(item, WaypointItemData):
            add(_CMD_NAV_WAYPOINT, item.latitude, item.longitude, item.altitude_m, p2=radius)
        elif isinstance(item, LoiterItemData):
            add(_CMD_NAV_LOITER_TIME, item.latitude, item.longitude, item.altitude_m, p1=item.hold_time_s, p2=radius)
        elif isinstance(item, LandItemData):
            add(_CMD_NAV_LAND, item.latitude, item.longitude, 0.0, p2=radius)
        elif isinstance(item, ChangeSpeedItemData):
            add(_CMD_DO_CHANGE_SPEED, 0.0, 0.0, 0.0, p1=1.0, p2=item.speed_ms)
        elif isinstance(item, RtlItemData):
            add(_CMD_NAV_RTL, 0.0, 0.0, 0.0)

    if not speed_inserted:
        # No Takeoff item in the list (not reachable from today's UI, which
        # always creates one via the Launch tool) — still apply the speed
        # near the start rather than dropping it.
        built.insert(1, WaypointItem(
            index=0, current=False, frame=_FRAME_GLOBAL_REL, command=_CMD_DO_CHANGE_SPEED,
            param1=1.0, param2=speed_ms, param3=0.0, param4=0.0,
            latitude=0.0, longitude=0.0, altitude=0.0, autocontinue=True,
        ))
        for i, w in enumerate(built):
            w.index = i

    if not has_rtl:
        # ArduPilot returns to the vehicle's true arm-location home
        # regardless of what the index-0 item above says.
        add(_CMD_NAV_RTL, 0.0, 0.0, 0.0)

    positional = [
        w for w in built
        if not w.current and (w.latitude != 0 or w.longitude != 0)
    ]
    total_m = _path_distance_m(positional)
    duration_s = total_m / max(speed_ms, 0.1)
    consumed_mah = (duration_s / 3600.0) * settings.CRUISE_CURRENT_AMPS * 1000.0
    battery_pct = min((consumed_mah / settings.DEFAULT_BATTERY_CAPACITY_MAH) * 100.0, 100.0)
    altitudes = [w.altitude for w in positional if w.altitude > 0]

    mission = Mission(
        filename=f"{mission_name}.plan" if mission_name else "manual_mission.plan",
        source_format="manual",
        waypoint_count=len(built),
        nav_waypoints=len(positional),
        total_distance_m=round(total_m, 1),
        total_distance_km=round(total_m / 1000.0, 3),
        estimated_duration_minutes=round(duration_s / 60.0, 1),
        estimated_battery_percent=round(battery_pct, 1),
        min_altitude_m=min(altitudes) if altitudes else 0.0,
        max_altitude_m=max(altitudes) if altitudes else 0.0,
        waypoints=built,
    )

    return mission, None
