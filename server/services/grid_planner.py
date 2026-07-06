"""Survey grid mission generator.

Turns a user-drawn polygon plus mapping parameters (altitude, speed,
overlaps, grid angle) into a lawnmower-pattern Mission ready for upload to
the Pixhawk.

Geometry is done in a local East/North metre frame (equirectangular
approximation around the polygon centroid) — accurate to well under a metre
for survey-sized areas.

Line spacing and photo spacing are derived from the camera's ground
footprint at the flight altitude:

    footprint_w = 2 * altitude * tan(HFOV / 2)      (across-track)
    footprint_h = 2 * altitude * tan(VFOV / 2)      (along-track)
    line spacing  = footprint_w * (1 - side_overlap)
    photo spacing = footprint_h * (1 - front_overlap)
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from config import settings
from models.mission import Mission, WaypointItem
from parser.waypoint_parser import _path_distance_m

logger = logging.getLogger(__name__)

_CMD_NAV_WAYPOINT = 16
_CMD_NAV_RTL = 20
_CMD_NAV_TAKEOFF = 22
_CMD_DO_CHANGE_SPEED = 178

_FRAME_GLOBAL = 0
_FRAME_GLOBAL_REL = 3

_MAX_GRID_WAYPOINTS = 900   # leave headroom under the 1000-item mission limit


class GridPlanError(ValueError):
    """Raised when a survey grid cannot be generated from the inputs."""


@dataclass
class GridParams:
    altitude_m: float
    speed_ms: float
    side_overlap_pct: float
    front_overlap_pct: float
    angle_deg: float

    def validate(self) -> None:
        if not 2.0 <= self.altitude_m <= 500.0:
            raise GridPlanError("Altitude must be between 2 and 500 m.")
        if not 0.5 <= self.speed_ms <= 25.0:
            raise GridPlanError("Speed must be between 0.5 and 25 m/s.")
        for name, v in (("Side", self.side_overlap_pct), ("Front", self.front_overlap_pct)):
            if not 0.0 <= v <= 95.0:
                raise GridPlanError(f"{name} overlap must be between 0 and 95 %.")


def camera_footprint_m(altitude_m: float) -> tuple[float, float]:
    """Ground footprint (width across-track, height along-track) in metres."""
    w = 2.0 * altitude_m * math.tan(math.radians(settings.CAMERA_HFOV_DEG) / 2.0)
    h = 2.0 * altitude_m * math.tan(math.radians(settings.CAMERA_VFOV_DEG) / 2.0)
    return w, h


def generate_grid_mission(
    polygon: list[tuple[float, float]],
    params: GridParams,
    home: tuple[float, float] | None = None,
    mission_name: str | None = None,
) -> tuple[Mission, dict]:
    """Build a lawnmower survey Mission over *polygon* ([(lat, lon), ...]).

    Returns (mission, plan_info) where plan_info carries the derived mapping
    numbers (line spacing, photo spacing, line count) for the frontend.
    """
    params.validate()
    if len(polygon) < 3:
        raise GridPlanError("Polygon needs at least 3 vertices.")

    # ── Local metre frame around the centroid ─────────────────────────────────
    lat0 = sum(p[0] for p in polygon) / len(polygon)
    lon0 = sum(p[1] for p in polygon) / len(polygon)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
    if m_per_deg_lon < 1.0:
        raise GridPlanError("Polygon too close to the poles.")

    def to_xy(lat: float, lon: float) -> tuple[float, float]:
        return ((lon - lon0) * m_per_deg_lon, (lat - lat0) * m_per_deg_lat)

    def to_ll(x: float, y: float) -> tuple[float, float]:
        return (lat0 + y / m_per_deg_lat, lon0 + x / m_per_deg_lon)

    poly_xy = [to_xy(lat, lon) for lat, lon in polygon]

    # ── Spacing from camera footprint + overlap ───────────────────────────────
    footprint_w, footprint_h = camera_footprint_m(params.altitude_m)
    line_spacing = max(1.0, footprint_w * (1.0 - params.side_overlap_pct / 100.0))
    photo_spacing = max(0.5, footprint_h * (1.0 - params.front_overlap_pct / 100.0))

    # ── Rotate the frame so grid lines run along +x ───────────────────────────
    theta = math.radians(params.angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)

    def rot(p: tuple[float, float]) -> tuple[float, float]:
        return (p[0] * cos_t + p[1] * sin_t, -p[0] * sin_t + p[1] * cos_t)

    def unrot(p: tuple[float, float]) -> tuple[float, float]:
        return (p[0] * cos_t - p[1] * sin_t, p[0] * sin_t + p[1] * cos_t)

    rot_poly = [rot(p) for p in poly_xy]
    min_y = min(p[1] for p in rot_poly)
    max_y = max(p[1] for p in rot_poly)

    # ── Sweep horizontal lines through the rotated polygon ────────────────────
    lines: list[tuple[tuple[float, float], tuple[float, float]]] = []
    y = min_y + line_spacing / 2.0
    reverse = False
    while y <= max_y:
        xs = _polygon_scanline_xs(rot_poly, y)
        # Pair up entry/exit crossings; keep the widest span per sweep line
        # (simple polygons yield exactly one span; concave ones may yield more —
        # flying the widest keeps the mission simple and safe).
        if len(xs) >= 2:
            x_start, x_end = xs[0], xs[-1]
            a, b = (x_end, y), (x_start, y)
            if not reverse:
                a, b = b, a
            lines.append((a, b))
            reverse = not reverse
        y += line_spacing

    if not lines:
        raise GridPlanError(
            "No grid lines fit inside the polygon — area too small for the "
            f"computed line spacing ({line_spacing:.1f} m). Reduce altitude "
            "or increase side overlap."
        )

    # ── Assemble waypoints ─────────────────────────────────────────────────────
    home_ll = home if home is not None else (lat0, lon0)

    # Flatten the serpentine into a single ordered point list (still in the
    # rotated local frame) before deciding which end to fly first — the sweep
    # geometry itself (lines, spacing, overlap, coverage) is untouched here.
    flat_xy: list[tuple[float, float]] = [unrot(pt) for a, b in lines for pt in (a, b)]

    # By construction the sweep above always starts at min_y (the geometric
    # bottom of the polygon along the sweep axis). Compare the user's
    # first-drawn vertex against that same axis — not raw XY distance, which
    # is dominated by the serpentine's alternating left/right endpoint and
    # would pick the wrong end for e.g. a top-right first click — and start
    # from whichever end (min_y or max_y) it's nearer to.
    first_drawn_y = rot(poly_xy[0])[1]
    if abs(first_drawn_y - max_y) < abs(first_drawn_y - min_y):
        flat_xy.reverse()

    flat_ll = [to_ll(x, y) for x, y in flat_xy]
    first_ll = flat_ll[0]

    waypoints: list[WaypointItem] = []

    def add(command: int, lat: float, lon: float, alt: float,
            frame: int = _FRAME_GLOBAL_REL, current: bool = False,
            p1: float = 0.0, p2: float = 0.0) -> None:
        waypoints.append(WaypointItem(
            index=len(waypoints), current=current, frame=frame, command=command,
            param1=p1, param2=p2, param3=0.0, param4=0.0,
            latitude=lat, longitude=lon, altitude=alt, autocontinue=True,
        ))

    hover_mode = settings.CAPTURE_STRATEGY == "hover"
    # The actual hold-at-waypoint hold is a dedicated MAV_CMD_NAV_LOITER_TIME
    # item, inserted uniformly for every mission (uploaded or generated) by
    # services/mission_enrichment.py — this stays at param1=0.0 here.
    hold_time_s = settings.HOVER_HOLD_TIME_S if hover_mode else 0.0

    # 0: home (AMSL frame, matching parser convention)
    add(_CMD_NAV_WAYPOINT, home_ll[0], home_ll[1], 0.0,
        frame=_FRAME_GLOBAL, current=True)
    # 1: takeoff at the actual launch position (current drone GPS fix if
    # connected, otherwise the planned home) — never at a survey waypoint.
    add(_CMD_NAV_TAKEOFF, home_ll[0], home_ll[1], params.altitude_m)
    # 2: set ground speed
    add(_CMD_DO_CHANGE_SPEED, 0.0, 0.0, 0.0, p1=1.0, p2=params.speed_ms)
    # 3+: fly from the launch position to Waypoint 1 (first_ll), then the
    # rest of the survey sweep in drawing-order-aware direction — each point
    # is a capture waypoint (loiter/hold item inserted by
    # services/mission_enrichment.py, not here).
    n_capture_points = 0
    for lat, lon in flat_ll:
        waypoints.append(WaypointItem(
            index=len(waypoints), current=False, frame=_FRAME_GLOBAL_REL,
            command=_CMD_NAV_WAYPOINT, param1=0.0, param2=0.0,
            param3=0.0, param4=0.0, latitude=lat, longitude=lon,
            altitude=params.altitude_m, autocontinue=True,
            is_capture_point=True,
        ))
        n_capture_points += 1
    # final: RTL
    add(_CMD_NAV_RTL, 0.0, 0.0, 0.0)

    if len(waypoints) > _MAX_GRID_WAYPOINTS:
        raise GridPlanError(
            f"Generated {len(waypoints)} waypoints (limit {_MAX_GRID_WAYPOINTS}). "
            "Reduce the area, lower the overlap, or fly higher."
        )

    # ── Mission summary (same estimation model as the file parsers) ───────────
    nav_points = [
        w for w in waypoints
        if w.command == _CMD_NAV_WAYPOINT and not w.current
        and (w.latitude != 0 or w.longitude != 0)
    ]
    total_m = _path_distance_m(nav_points)
    hold_time_total_s = n_capture_points * hold_time_s
    duration_s = total_m / max(params.speed_ms, 0.1) + hold_time_total_s
    consumed_mah = (duration_s / 3600.0) * settings.CRUISE_CURRENT_AMPS * 1000.0
    battery_pct = min((consumed_mah / settings.DEFAULT_BATTERY_CAPACITY_MAH) * 100.0, 100.0)

    mission = Mission(
        filename=f"{mission_name}.plan" if mission_name else "generated_grid.plan",
        source_format="grid",
        waypoint_count=len(waypoints),
        nav_waypoints=len(nav_points),
        total_distance_m=round(total_m, 1),
        total_distance_km=round(total_m / 1000.0, 3),
        estimated_duration_minutes=round(duration_s / 60.0, 1),
        estimated_battery_percent=round(battery_pct, 1),
        min_altitude_m=params.altitude_m,
        max_altitude_m=params.altitude_m,
        waypoints=waypoints,
    )

    estimated_photos = (
        n_capture_points if hover_mode else max(1, int(total_m / photo_spacing))
    )

    plan_info = {
        "line_count": len(lines),
        "line_spacing_m": round(line_spacing, 2),
        "photo_spacing_m": round(photo_spacing, 2),
        "footprint_width_m": round(footprint_w, 2),
        "footprint_height_m": round(footprint_h, 2),
        "estimated_photos": estimated_photos,
        "capture_mode": settings.CAPTURE_STRATEGY,
        "hold_time_s": round(hold_time_s, 2),
        "capture_waypoint_count": n_capture_points,
        "hold_time_total_s": round(hold_time_total_s, 1),
    }

    logger.info(
        "Grid generated: %d lines, %d waypoints, %.0f m, spacing %.1f m, "
        "capture=%s (%d points, %.1fs hold each).",
        len(lines), len(waypoints), total_m, line_spacing,
        settings.CAPTURE_STRATEGY, n_capture_points, hold_time_s,
    )
    return mission, plan_info


def _polygon_scanline_xs(poly: list[tuple[float, float]], y: float) -> list[float]:
    """X coordinates where the horizontal line at *y* crosses the polygon edges."""
    xs: list[float] = []
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 <= y < y2) or (y2 <= y < y1):
            t = (y - y1) / (y2 - y1)
            xs.append(x1 + t * (x2 - x1))
    return sorted(xs)
