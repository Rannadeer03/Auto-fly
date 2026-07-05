"""Mission enrichment: densify sparse waypoint legs and insert native
ArduPilot loiter/capture mission items.

Applied uniformly to every mission before upload — whether it came from an
uploaded .plan/.waypoints file or from the survey grid generator — so a
mission with only a few widely-spaced waypoints doesn't fly point-to-point
with no intermediate capture positions. Two things happen to every leg
between real flight-path waypoints (home/takeoff/DO_*/RTL/LAND are left
untouched):

  1. If a leg is longer than the configured spacing (PHOTO_DISTANCE_M by
     default), extra NAV_WAYPOINT capture points are interpolated along it.
  2. Every capture waypoint gets a dedicated MAV_CMD_NAV_LOITER_TIME item
     right after it (a standard ArduPilot mission command) instead of the
     old approach of stuffing a hold time into NAV_WAYPOINT's own param1.
     ArduCopter only reports MISSION_ITEM_REACHED for a LOITER_TIME item
     once its hold duration has actually elapsed, so capture_strategies.py
     keys the shutter trigger off that item's seq.
"""
from __future__ import annotations

import logging

from config import settings
from models.mission import Mission, WaypointItem
from parser.waypoint_parser import WaypointParseError, _path_distance_m, haversine_m

logger = logging.getLogger(__name__)

_CMD_NAV_WAYPOINT = 16
_CMD_NAV_LOITER_TIME = 19
_CMD_DO_CHANGE_SPEED = 178
_MAX_MISSION_ITEMS = 1000  # MAVLink mission protocol hard limit


def _is_nav_point(w: WaypointItem) -> bool:
    """A real flight-path point — excludes home (index 0/current) and
    non-NAV_WAYPOINT items (takeoff, DO_*, RTL/LAND)."""
    return w.command == _CMD_NAV_WAYPOINT and not w.current and (w.latitude != 0 or w.longitude != 0)


def _max_spacing_m() -> float:
    """Maximum distance between consecutive hover-capture stops.

    Deliberately reuses PHOTO_DISTANCE_M (already "distance between
    individual photos" elsewhere in this codebase) rather than the
    continuous-mode overlap formula (camera_footprint_m * (1-overlap)) —
    that formula is calibrated for photos taken while still flying, and at
    typical mapping altitudes/overlap it works out to only a few metres,
    which would turn a sparse mission into dozens of full stop-loiter-
    capture cycles a few metres apart.
    """
    if settings.MAX_WAYPOINT_SPACING_M is not None:
        return settings.MAX_WAYPOINT_SPACING_M
    return max(0.5, settings.PHOTO_DISTANCE_M)


def _interior_points(a: WaypointItem, b: WaypointItem) -> list[tuple[float, float, float]]:
    """Evenly-spaced (lat, lon, alt) points strictly between a and b, only if
    the leg is longer than the configured max spacing."""
    dist = haversine_m(a.latitude, a.longitude, b.latitude, b.longitude)
    spacing = _max_spacing_m()
    if dist <= spacing:
        return []
    count = int(dist // spacing)
    return [
        (
            a.latitude + (b.latitude - a.latitude) * (k / (count + 1)),
            a.longitude + (b.longitude - a.longitude) * (k / (count + 1)),
            a.altitude + (b.altitude - a.altitude) * (k / (count + 1)),
        )
        for k in range(1, count + 1)
    ]


def _strip_previous_loiter_items(waypoints: list[WaypointItem]) -> list[WaypointItem]:
    """Undo a prior enrichment pass's loiter insertion.

    Without this, calling enrich_mission twice on the same mission (e.g. a
    mission stored via store_mission() and later re-enriched) would keep
    each old MAV_CMD_NAV_LOITER_TIME item as an ordinary pass-through item
    *and* insert a fresh one next to it, silently doubling every loiter
    item on each additional pass.
    """
    out: list[WaypointItem] = []
    for i, w in enumerate(waypoints):
        if (
            w.command == _CMD_NAV_LOITER_TIME
            and i > 0
            and waypoints[i - 1].command == _CMD_NAV_WAYPOINT
            and waypoints[i - 1].latitude == w.latitude
            and waypoints[i - 1].longitude == w.longitude
        ):
            continue
        out.append(w)
    return out


def enrich_mission(mission: Mission) -> Mission:
    """Return a new Mission with densified legs and explicit loiter items.

    A mission with fewer than one real nav waypoint (e.g. a bare
    takeoff+RTL) is returned unchanged — there's nothing to densify.

    Only applies in "hover" capture mode. In "continuous" mode the vehicle
    is deliberately never meant to stop — photos are triggered by distance
    or time while flying (ContinuousCaptureStrategy) — so inserting stop-
    and-loiter items would be wrong there; the mission passes through as-is.
    """
    if settings.CAPTURE_STRATEGY != "hover":
        return mission

    waypoints = _strip_previous_loiter_items(mission.waypoints)
    nav_indices = {i for i, w in enumerate(waypoints) if _is_nav_point(w)}
    if not nav_indices:
        return mission

    out: list[WaypointItem] = []

    def emit(w: WaypointItem) -> None:
        out.append(w.model_copy(update={"index": len(out)}))

    def emit_capture_point(template: WaypointItem, lat: float, lon: float, alt: float) -> None:
        """Emit a NAV_WAYPOINT arrival followed by the native loiter hold
        that marks the actual capture trigger (see capture_strategies.py)."""
        emit(template.model_copy(update={
            "latitude": lat, "longitude": lon, "altitude": alt,
            "command": _CMD_NAV_WAYPOINT, "param1": 0.0,
            "is_capture_point": False, "current": False,
        }))
        emit(WaypointItem(
            index=0, current=False, frame=template.frame, command=_CMD_NAV_LOITER_TIME,
            param1=settings.HOVER_HOLD_TIME_S, param2=0.0, param3=0.0, param4=0.0,
            latitude=lat, longitude=lon, altitude=alt,
            autocontinue=True, is_capture_point=True,
        ))

    n = len(waypoints)
    for i, w in enumerate(waypoints):
        if i not in nav_indices:
            emit(w)
            continue

        emit_capture_point(w, w.latitude, w.longitude, w.altitude)

        j = i + 1
        while j < n and j not in nav_indices:
            j += 1
        if j < n:
            for lat, lon, alt in _interior_points(w, waypoints[j]):
                emit_capture_point(w, lat, lon, alt)

    if len(out) > _MAX_MISSION_ITEMS:
        raise WaypointParseError(
            f"Densifying this mission produces {len(out)} waypoints "
            f"(limit {_MAX_MISSION_ITEMS}). Reduce the flight altitude "
            "(smaller camera footprint) or shorten the legs between waypoints."
        )

    nav_points = [w for w in out if w.command == _CMD_NAV_WAYPOINT and not w.current]
    capture_count = sum(1 for w in out if w.is_capture_point)
    total_m = _path_distance_m(nav_points)
    # Same convention as the parsers/grid_planner: read the mission's own
    # DO_CHANGE_SPEED item rather than back-deriving speed from the
    # pre-enrichment distance/duration estimate (fragile at the edges,
    # e.g. a mission with no distance yet).
    cruise_speed = settings.DEFAULT_CRUISE_SPEED_MS
    for w in out:
        if w.command == _CMD_DO_CHANGE_SPEED and w.param2 > 0:
            cruise_speed = w.param2
            break
    duration_s = total_m / max(cruise_speed, 0.1) + capture_count * settings.HOVER_HOLD_TIME_S
    consumed_mah = (duration_s / 3600.0) * settings.CRUISE_CURRENT_AMPS * 1000.0
    battery_pct = min((consumed_mah / settings.DEFAULT_BATTERY_CAPACITY_MAH) * 100.0, 100.0)

    logger.info(
        "Mission enriched: %d -> %d waypoints (%d capture points, %.0f m).",
        len(waypoints), len(out), capture_count, total_m,
    )

    return mission.model_copy(update={
        "waypoints": out,
        "waypoint_count": len(out),
        "nav_waypoints": len(nav_points),
        "total_distance_m": round(total_m, 1),
        "total_distance_km": round(total_m / 1000.0, 3),
        "estimated_duration_minutes": round(duration_s / 60.0, 1),
        "estimated_battery_percent": round(battery_pct, 1),
    })
