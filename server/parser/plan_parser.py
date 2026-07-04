"""
QGroundControl Plan (.plan) file parser.

.plan files are JSON documents produced by QGroundControl.
Schema (version 1 wrapper, mission version 2):

{
  "fileType": "Plan",
  "version": 1,
  "groundStation": "QGroundControl",
  "mission": {
    "version": 2,
    "hoverSpeed": 5,
    "cruiseSpeed": 15,
    "plannedHomePosition": [lat, lon, alt_amsl],
    "items": [
      {
        "type": "SimpleItem",
        "autoContinue": true,
        "command": 16,
        "frame": 3,
        "params": [p1, p2, p3, p4, lat, lon, alt]   <- null allowed
      },
      {
        "type": "ComplexItem",        <- survey/corridor, skipped in V1
        ...
      }
    ]
  }
}

ComplexItems (survey areas, corridors) are logged and skipped; only
SimpleItems are extracted.  The plannedHomePosition is prepended as
index-0 with current=True, matching the .waypoints convention.
"""
import json
import logging
from pathlib import Path

from models.mission import Mission, WaypointItem
from parser.waypoint_parser import WaypointParseError, _path_distance_m

logger = logging.getLogger(__name__)

_CMD_NAV_WAYPOINT  = 16
_CMD_DO_CHANGE_SPEED = 178

# MAV_FRAME values used when building waypoints
_FRAME_GLOBAL     = 0   # altitude is AMSL
_FRAME_GLOBAL_REL = 3   # altitude is relative to home (most common in .plan)


class QGCPlanParser:
    """Stateless parser for QGroundControl .plan (JSON) files."""

    def parse_bytes(self, data: bytes, filename: str = "mission.plan") -> Mission:
        """Parse raw file bytes and return a validated Mission."""
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WaypointParseError("File is not valid UTF-8 text.") from exc
        return self._parse(text, filename)

    # ── Top-level ──────────────────────────────────────────────────────────────

    def _parse(self, text: str, filename: str) -> Mission:
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise WaypointParseError(f"Invalid JSON in .plan file: {exc}") from exc

        self._validate_document(doc)
        mission_doc = doc["mission"]

        waypoints = self._extract_waypoints(mission_doc)

        if not waypoints:
            raise WaypointParseError("No usable waypoints found in .plan file.")
        if len(waypoints) > 1000:
            raise WaypointParseError(
                f"Mission has {len(waypoints)} waypoints; limit is 1000."
            )

        return self._build_mission(waypoints, filename, mission_doc)

    # ── Validation ─────────────────────────────────────────────────────────────

    def _validate_document(self, doc: dict) -> None:
        if not isinstance(doc, dict):
            raise WaypointParseError("Top-level JSON value must be an object.")
        if doc.get("fileType") != "Plan":
            raise WaypointParseError(
                f"Not a QGroundControl Plan file (fileType='{doc.get('fileType')}')."
            )
        if "mission" not in doc:
            raise WaypointParseError("Missing 'mission' key in .plan file.")
        mission_version = doc["mission"].get("version")
        if mission_version not in (2, "2"):
            logger.warning(
                "Unexpected plan mission version '%s' — parsing anyway.", mission_version
            )

    # ── Waypoint extraction ────────────────────────────────────────────────────

    def _extract_waypoints(self, mission_doc: dict) -> list[WaypointItem]:
        waypoints: list[WaypointItem] = []

        # Index 0: home position (matches .waypoints convention)
        home = mission_doc.get("plannedHomePosition")
        if home and len(home) >= 3:
            waypoints.append(
                WaypointItem(
                    index=0,
                    current=True,
                    frame=_FRAME_GLOBAL,          # home is always AMSL
                    command=_CMD_NAV_WAYPOINT,
                    param1=0.0, param2=0.0, param3=0.0, param4=0.0,
                    latitude=float(home[0]),
                    longitude=float(home[1]),
                    altitude=float(home[2]),
                    autocontinue=True,
                )
            )

        skipped_complex = 0
        for item in mission_doc.get("items", []):
            if item.get("type", "SimpleItem") == "SimpleItem":
                seq = len(waypoints)
                waypoints.append(self._parse_simple_item(item, seq))
            else:
                skipped_complex += 1
                logger.warning(
                    "Skipping unsupported ComplexItem (complexItemType='%s').",
                    item.get("complexItemType", "unknown"),
                )

        if skipped_complex:
            logger.warning(
                "%d ComplexItem(s) were skipped — only SimpleItems are supported in V1.",
                skipped_complex,
            )

        return waypoints

    def _parse_simple_item(self, item: dict, seq: int) -> WaypointItem:
        raw_params = item.get("params", [])
        # Normalise length to exactly 7 and replace JSON null with 0.0
        params = [float(v) if v is not None else 0.0 for v in raw_params]
        while len(params) < 7:
            params.append(0.0)

        return WaypointItem(
            index=seq,
            current=False,
            frame=int(item.get("frame", _FRAME_GLOBAL_REL)),
            command=int(item.get("command", _CMD_NAV_WAYPOINT)),
            param1=params[0],
            param2=params[1],
            param3=params[2],
            param4=params[3],
            latitude=params[4],
            longitude=params[5],
            altitude=params[6],
            autocontinue=bool(item.get("autoContinue", True)),
        )

    # ── Mission summary ────────────────────────────────────────────────────────

    def _build_mission(
        self, waypoints: list[WaypointItem], filename: str, mission_doc: dict
    ) -> Mission:
        nav_points = [
            w for w in waypoints
            if w.command == _CMD_NAV_WAYPOINT
            and not w.current                        # exclude home position (index 0)
            and (w.latitude != 0 or w.longitude != 0)
        ]

        total_m = _path_distance_m(nav_points)

        # Prefer hoverSpeed from the plan; fall back to cruiseSpeed then 5 m/s
        cruise_speed = float(
            mission_doc.get("hoverSpeed")
            or mission_doc.get("cruiseSpeed")
            or 5.0
        )
        # A DO_CHANGE_SPEED command overrides the plan-level speed
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
            source_format="plan",
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
