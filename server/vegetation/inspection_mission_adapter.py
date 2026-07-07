"""InspectionMissionAdapter.

Converts a MissionCandidate domain model into the canonical internal Mission
format used by the rest of the application (Manual/Survey missions, UI, MAVLink).
"""

from models.mission import Mission, WaypointItem
from vegetation.mission_candidate import MissionCandidate

# Standard MAVLink Constants
MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
MAV_CMD_NAV_TAKEOFF = 22
MAV_FRAME_GLOBAL_RELATIVE_ALT = 3


class InspectionMissionAdapter:
    """Adapts MissionCandidate to the canonical Mission model."""

    @staticmethod
    def to_canonical_mission(candidate: MissionCandidate) -> Mission:
        """Convert MissionCandidate to a models.mission.Mission."""
        waypoints = []
        
        # 1. Home waypoint (Required by MAVLink specification at Index 0)
        # We leave lat/lon as 0 to denote "use current home".
        waypoints.append(WaypointItem(
            index=0,
            current=False,
            frame=0,
            command=MAV_CMD_NAV_WAYPOINT,
            param1=0.0, param2=0.0, param3=0.0, param4=0.0,
            latitude=0.0,
            longitude=0.0,
            altitude=0.0,
            autocontinue=True,
            is_capture_point=False
        ))
        
        # 2. Takeoff
        takeoff_alt = candidate.waypoints[0].altitude if candidate.waypoints else 10.0
        waypoints.append(WaypointItem(
            index=1,
            current=False,
            frame=MAV_FRAME_GLOBAL_RELATIVE_ALT,
            command=MAV_CMD_NAV_TAKEOFF,
            param1=0.0, param2=0.0, param3=0.0, param4=0.0,
            latitude=0.0,
            longitude=0.0,
            altitude=takeoff_alt,
            autocontinue=True,
            is_capture_point=False
        ))
        
        # 3. Inspection Waypoints (Hover)
        idx = 2
        for cw in candidate.waypoints:
            waypoints.append(WaypointItem(
                index=idx,
                current=False,
                frame=MAV_FRAME_GLOBAL_RELATIVE_ALT,
                command=MAV_CMD_NAV_WAYPOINT,
                param1=cw.hover_time,  # Hold time in seconds
                param2=0.0,
                param3=0.0,
                param4=0.0,
                latitude=cw.latitude,
                longitude=cw.longitude,
                altitude=cw.altitude,
                autocontinue=True,
                is_capture_point=True  # Used by UI to render camera icon
            ))
            idx += 1
            
        # 4. RTL (Optional)
        if candidate.rtl:
            waypoints.append(WaypointItem(
                index=idx,
                current=False,
                frame=MAV_FRAME_GLOBAL_RELATIVE_ALT,
                command=MAV_CMD_NAV_RETURN_TO_LAUNCH,
                param1=0.0, param2=0.0, param3=0.0, param4=0.0,
                latitude=0.0,
                longitude=0.0,
                altitude=0.0,
                autocontinue=True,
                is_capture_point=False
            ))
            idx += 1
            
        # Calculate derived metrics
        dur_mins = candidate.estimated_duration_sec / 60.0
        
        # Very rough battery heuristic (just for UI placeholder, 10% per min)
        # We reuse the same logic that existing mission exporters probably use,
        # but since we are self-contained here, we supply a basic estimate.
        est_batt = min(100.0, dur_mins * 5.0) 
        
        min_alt = min((wp.altitude for wp in candidate.waypoints), default=0.0)
        max_alt = max((wp.altitude for wp in candidate.waypoints), default=0.0)
        
        # Format filename to indicate this is an auto-generated inspection mission
        filename = f"inspection_{candidate.source_mission_id}_{candidate.mission_id[:8]}.plan"

        return Mission(
            filename=filename,
            source_format="plan",
            waypoint_count=len(waypoints),
            nav_waypoints=len(candidate.waypoints),
            total_distance_m=candidate.estimated_distance_m,
            total_distance_km=candidate.estimated_distance_m / 1000.0,
            estimated_duration_minutes=dur_mins,
            estimated_battery_percent=est_batt,
            min_altitude_m=min_alt,
            max_altitude_m=max_alt,
            waypoints=waypoints
        )
