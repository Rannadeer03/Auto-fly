"""ProjectionResult — Estimated ground position of an observation.

Phase 3E.5 output. Stored in MissionSessionContext alongside the track.
"""

from dataclasses import dataclass

@dataclass
class ProjectionResult:
    """Estimated WGS84 ground position of a vegetation patch."""
    
    latitude: float
    longitude: float
    ground_offset_x_m: float       # Right offset from drone in meters
    ground_offset_y_m: float       # Forward offset from drone in meters
    ground_distance_m: float       # Straight line distance from drone nadir
    bearing_deg: float             # Bearing from drone to target (0-360)
    estimated_error_m: float       # Rough uncertainty bound
    projection_timestamp: float    # time.time() of calculation
