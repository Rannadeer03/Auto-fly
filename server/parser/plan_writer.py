"""
QGroundControl Plan (.plan) file writer — the inverse of parser/plan_parser.py.

Produces a standard QGC v1/v2 .plan document from a Mission, so missions
saved in this app's library can be opened directly in QGroundControl (and
re-parsed by our own plan_parser.py, round-tripping cleanly).
"""
from __future__ import annotations

import json

from models.mission import Mission

_CMD_NAV_WAYPOINT = 16


def mission_to_plan_dict(mission: Mission, cruise_speed_ms: float = 5.0) -> dict:
    """Build a QGC .plan document (as a dict) from a Mission.

    Mission.waypoints[0] is this app's home-position convention (current=True,
    AMSL frame) and becomes plannedHomePosition; every remaining item becomes
    a SimpleItem.
    """
    waypoints = mission.waypoints
    home = waypoints[0] if waypoints and waypoints[0].current else None
    items = waypoints[1:] if home else waypoints

    plan_items = []
    for i, w in enumerate(items):
        plan_items.append({
            "AMSLAltAboveTerrain": None,
            "Altitude": w.altitude,
            "AltitudeMode": 1,
            "autoContinue": w.autocontinue,
            "command": w.command,
            "doJumpId": i + 1,
            "frame": w.frame,
            "params": [w.param1, w.param2, w.param3, w.param4, w.latitude, w.longitude, w.altitude],
            "type": "SimpleItem",
        })

    return {
        "fileType": "Plan",
        "version": 1,
        "groundStation": "QGroundControl",
        "geoFence": {"circles": [], "polygons": [], "version": 2},
        "rallyPoints": {"points": [], "version": 2},
        "mission": {
            "version": 2,
            "firmwareType": 3,   # MAV_AUTOPILOT_ARDUPILOTMEGA
            "vehicleType": 2,    # MAV_TYPE_QUADROTOR
            "cruiseSpeed": cruise_speed_ms,
            "hoverSpeed": cruise_speed_ms,
            "plannedHomePosition": (
                [home.latitude, home.longitude, home.altitude] if home else None
            ),
            "items": plan_items,
        },
    }


def mission_to_plan_bytes(mission: Mission, cruise_speed_ms: float = 5.0) -> bytes:
    return json.dumps(mission_to_plan_dict(mission, cruise_speed_ms), indent=2).encode("utf-8")
