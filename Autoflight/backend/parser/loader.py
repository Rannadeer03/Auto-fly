"""
Mission file loader — selects the correct parser based on file extension.

Usage:
    from parser.loader import load_mission
    mission = load_mission("survey.plan", raw_bytes)
    mission = load_mission("field_run.waypoints", raw_bytes)

Both calls return a Mission object with identical structure.
The rest of the system never needs to know which format was used.
"""
from pathlib import Path

from models.mission import Mission
from parser.plan_parser import QGCPlanParser
from parser.waypoint_parser import QGCWaypointParser, WaypointParseError

_PARSERS: dict[str, type] = {
    ".waypoints": QGCWaypointParser,
    ".plan":      QGCPlanParser,
}


def load_mission(filename: str, data: bytes) -> Mission:
    """Parse *data* as a mission file, choosing the parser from *filename*'s extension.

    Args:
        filename: Original filename — used only for extension detection and the
                  Mission.filename field.  Must end in .waypoints or .plan.
        data:     Raw file bytes.

    Returns:
        A fully populated Mission object.

    Raises:
        WaypointParseError: File format is unsupported, malformed, or fails validation.
    """
    ext = Path(filename).suffix.lower()
    parser_cls = _PARSERS.get(ext)
    if parser_cls is None:
        supported = ", ".join(sorted(_PARSERS))
        raise WaypointParseError(
            f"Unsupported file format '{ext}'. Supported formats: {supported}."
        )
    return parser_cls().parse_bytes(data, filename)


def supported_extensions() -> list[str]:
    """Return the list of file extensions this loader accepts."""
    return sorted(_PARSERS)
