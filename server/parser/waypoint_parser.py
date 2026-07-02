"""
QGroundControl Waypoint (.waypoints) file parser.

Format: QGC WPL 110
Each data line: index current frame command p1 p2 p3 p4 lat lon alt autocontinue
Columns are tab-separated (falls back to whitespace).
"""
import math
from pathlib import Path
from models.mission import Mission, WaypointItem

# MAVLink command IDs relevant to path planning
_CMD_NAV_WAYPOINT = 16
_CMD_NAV_RTL = 20
_CMD_NAV_LAND = 21
_CMD_NAV_TAKEOFF = 22
_CMD_DO_CHANGE_SPEED = 178

_EXPECTED_COLUMNS = 12
_SUPPORTED_VERSION = 110


class WaypointParseError(ValueError):
    """Raised when a mission file fails parsing or validation.

    Re-used by plan_parser and loader — kept here as the canonical definition.
    """


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two WGS-84 points."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(max(0.0, a)))


class QGCWaypointParser:
    """Stateless parser for QGC WPL 110 mission files."""

    def parse_bytes(self, data: bytes, filename: str = "mission.waypoints") -> Mission:
        """Parse raw file bytes and return a validated Mission."""
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WaypointParseError("File is not valid UTF-8 text.") from exc
        return self._parse(text, filename)

    def _parse(self, text: str, filename: str) -> Mission:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if not lines:
            raise WaypointParseError("File is empty.")

        self._validate_header(lines[0])

        data_lines = [ln for ln in lines[1:] if not ln.startswith("#")]
        if not data_lines:
            raise WaypointParseError("No waypoints found in file.")

        waypoints = [self._parse_line(ln, i + 2) for i, ln in enumerate(data_lines)]

        if len(waypoints) > 1000:
            raise WaypointParseError(
                f"Mission has {len(waypoints)} waypoints; limit is 1000."
            )

        return self._build_mission(waypoints, filename)

    # ── Header ─────────────────────────────────────────────────────────────────

    def _validate_header(self, line: str) -> None:
        parts = line.split()
        if len(parts) < 3 or parts[0] != "QGC" or parts[1] != "WPL":
            raise WaypointParseError(
                f"Unrecognised file header: '{line}'. Expected 'QGC WPL 110'."
            )
        try:
            version = int(parts[2])
        except ValueError as exc:
            raise WaypointParseError(f"Non-integer version in header: '{parts[2]}'.") from exc
        if version != _SUPPORTED_VERSION:
            raise WaypointParseError(
                f"Unsupported QGC WPL version {version}. Only version {_SUPPORTED_VERSION} is supported."
            )

    # ── Line parsing ───────────────────────────────────────────────────────────

    def _parse_line(self, line: str, line_num: int) -> WaypointItem:
        cols = line.split("\t")
        if len(cols) != _EXPECTED_COLUMNS:
            cols = line.split()
        if len(cols) != _EXPECTED_COLUMNS:
            raise WaypointParseError(
                f"Line {line_num}: expected {_EXPECTED_COLUMNS} columns, got {len(cols)}."
            )
        try:
            return WaypointItem(
                index=int(cols[0]),
                current=bool(int(cols[1])),
                frame=int(cols[2]),
                command=int(cols[3]),
                param1=float(cols[4]),
                param2=float(cols[5]),
                param3=float(cols[6]),
                param4=float(cols[7]),
                latitude=float(cols[8]),
                longitude=float(cols[9]),
                altitude=float(cols[10]),
                autocontinue=bool(int(cols[11])),
            )
        except (ValueError, IndexError) as exc:
            raise WaypointParseError(f"Line {line_num}: cannot parse values — {exc}.") from exc

    # ── Mission builder ────────────────────────────────────────────────────────

    def _build_mission(self, waypoints: list[WaypointItem], filename: str) -> Mission:
        nav_points = [
            w for w in waypoints
            if w.command == _CMD_NAV_WAYPOINT
            and not w.current                        # exclude home position (index 0)
            and (w.latitude != 0 or w.longitude != 0)
        ]

        total_m = _path_distance_m(nav_points)

        cruise_speed = 5.0
        for w in waypoints:
            if w.command == _CMD_DO_CHANGE_SPEED and w.param2 > 0:
                cruise_speed = w.param2
                break

        duration_s = total_m / max(cruise_speed, 0.1)
        pack_mah = 16_000.0
        consumed_mah = (duration_s / 3600.0) * 20.0 * 1000.0
        battery_pct = min((consumed_mah / pack_mah) * 100.0, 100.0)

        altitudes = [w.altitude for w in waypoints if w.altitude > 0]

        return Mission(
            filename=Path(filename).name,
            source_format="waypoints",
            waypoint_count=len(waypoints),
            nav_waypoints=len(nav_points),
            total_distance_m=round(total_m, 1),
            total_distance_km=round(total_m / 1000.0, 3),
            estimated_duration_minutes=round(duration_s / 60.0, 1),
            estimated_battery_percent=round(battery_pct, 1),
            min_altitude_m=min(altitudes) if altitudes else 0.0,
            max_altitude_m=max(altitudes) if altitudes else 0.0,
            waypoints=waypoints,
        )


def _path_distance_m(nav: list[WaypointItem]) -> float:
    """Sum of haversine distances along a sequence of nav waypoints."""
    total = 0.0
    for i in range(1, len(nav)):
        total += haversine_m(
            nav[i - 1].latitude, nav[i - 1].longitude,
            nav[i].latitude,     nav[i].longitude,
        )
    return total
