"""Mission Candidate Domain Model.

Represents a proposed inspection mission generated from a set of Anomalies.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class InspectionWaypoint:
    """A single waypoint to inspect a detected anomaly."""
    sequence: int
    latitude: float
    longitude: float
    altitude: float
    hover_time: float
    source_anomaly_id: str
    severity: float
    confidence: float
    merged_anomaly_ids: List[str] = field(default_factory=list)


@dataclass
class MissionCandidate:
    """A proposed flight plan to inspect severe anomalies."""
    mission_id: str
    mission_type: str
    source_mission_id: str
    created_at: float
    total_anomalies: int
    merged_anomalies: int
    hover_time_sec: float
    rtl: bool
    estimated_distance_m: float
    estimated_duration_sec: float
    waypoints: List[InspectionWaypoint] = field(default_factory=list)
