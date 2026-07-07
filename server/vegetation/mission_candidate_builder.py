"""MissionCandidateBuilder.

Filters, merges, and sequences anomalies into an optimized inspection mission.
"""

import copy
import math
import time
import uuid
from typing import List

from config import settings
from vegetation.anomaly import Anomaly
from vegetation.mission_candidate import InspectionWaypoint, MissionCandidate


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points on earth in meters."""
    R = 6378137.0  # Earth radius in meters (WGS84)
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (math.sin(dphi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return R * c


class MissionCandidateBuilder:
    """Builds a MissionCandidate from a list of Anomalies."""

    @staticmethod
    def build(anomalies: List[Anomaly], start_lat: float, start_lon: float, source_mission_id: str) -> MissionCandidate:
        """Filter, merge, and route anomalies to produce a mission candidate."""
        # 1. Filter
        filtered = [
            a for a in anomalies
            if a.severity >= settings.MISSION_CANDIDATE_MIN_SEVERITY
            and a.confidence >= settings.MISSION_CANDIDATE_MIN_CONFIDENCE
        ]
        
        # 2. Merge nearby
        merged_anomalies: List[Anomaly] = []
        merge_radius = settings.MISSION_CANDIDATE_MERGE_RADIUS_M
        
        for a in filtered:
            merged = False
            lat = a.projection_result.latitude
            lon = a.projection_result.longitude
            
            for m in merged_anomalies:
                m_lat = m.projection_result.latitude
                m_lon = m.projection_result.longitude
                dist = _haversine_distance(lat, lon, m_lat, m_lon)
                
                if dist <= merge_radius:
                    # Keep track of merged IDs
                    if not hasattr(m, "_merged_ids"):
                        m._merged_ids = []
                    m._merged_ids.append(a.anomaly_id)
                    
                    # Update merged anomaly to take the higher severity representation
                    if a.severity > m.severity:
                        m.severity = a.severity
                        m.confidence = max(m.confidence, a.confidence)
                        m.projection_result.latitude = lat
                        m.projection_result.longitude = lon
                        m.anomaly_id = a.anomaly_id # retain the most severe ID
                    merged = True
                    break
                    
            if not merged:
                cand = copy.deepcopy(a)
                cand._merged_ids = []
                merged_anomalies.append(cand)
                
        merged_count = len(filtered) - len(merged_anomalies)
                
        # 3. Nearest-Neighbor Routing
        waypoints: List[InspectionWaypoint] = []
        if not merged_anomalies:
            return MissionCandidate(
                mission_id=str(uuid.uuid4()),
                mission_type="INSPECTION",
                source_mission_id=source_mission_id,
                created_at=time.time(),
                total_anomalies=len(anomalies),
                merged_anomalies=0,
                hover_time_sec=settings.MISSION_CANDIDATE_HOVER_TIME_SEC,
                rtl=settings.MISSION_CANDIDATE_RTL,
                estimated_distance_m=0.0,
                estimated_duration_sec=0.0,
                waypoints=[]
            )
            
        unvisited = merged_anomalies.copy()
        
        # Start nearest-neighbor from the launch/home position
        ordered = []
        c_lat, c_lon = start_lat, start_lon
        
        while unvisited:
            
            closest_idx = 0
            min_dist = float('inf')
            
            for i, cand in enumerate(unvisited):
                dist = _haversine_distance(
                    c_lat, c_lon,
                    cand.projection_result.latitude, cand.projection_result.longitude
                )
                if dist < min_dist:
                    min_dist = dist
                    closest_idx = i
                    
            current = unvisited.pop(closest_idx)
            ordered.append(current)
            c_lat = current.projection_result.latitude
            c_lon = current.projection_result.longitude
            
        # 4. Generate Waypoints and Estimate Distance/Time
        seq = 0
        total_dist_m = 0.0
        
        # Add distance from start position to the first waypoint
        if ordered:
            total_dist_m += _haversine_distance(
                start_lat, start_lon, 
                ordered[0].projection_result.latitude, ordered[0].projection_result.longitude
            )
        
        for i, a in enumerate(ordered):
            seq += 1
            if i > 0:
                prev = ordered[i-1]
                total_dist_m += _haversine_distance(
                    prev.projection_result.latitude, prev.projection_result.longitude,
                    a.projection_result.latitude, a.projection_result.longitude
                )
                
            wp = InspectionWaypoint(
                sequence=seq,
                latitude=a.projection_result.latitude,
                longitude=a.projection_result.longitude,
                altitude=settings.MISSION_CANDIDATE_INSPECTION_ALTITUDE_M,
                hover_time=settings.MISSION_CANDIDATE_HOVER_TIME_SEC,
                source_anomaly_id=a.anomaly_id,
                merged_anomaly_ids=getattr(a, '_merged_ids', []),
                severity=a.severity,
                confidence=a.confidence
            )
            waypoints.append(wp)
            
        # 5. Estimate Duration
        # Flight time = distance / cruise speed
        # Hover time = hover_time * num_waypoints
        flight_sec = total_dist_m / settings.DEFAULT_CRUISE_SPEED_MS
        hover_sec = len(waypoints) * settings.MISSION_CANDIDATE_HOVER_TIME_SEC
        total_sec = flight_sec + hover_sec
        
        return MissionCandidate(
            mission_id=str(uuid.uuid4()),
            mission_type="INSPECTION",
            source_mission_id=source_mission_id,
            created_at=time.time(),
            total_anomalies=len(anomalies),
            merged_anomalies=merged_count,
            hover_time_sec=settings.MISSION_CANDIDATE_HOVER_TIME_SEC,
            rtl=settings.MISSION_CANDIDATE_RTL,
            estimated_distance_m=round(total_dist_m, 2),
            estimated_duration_sec=round(total_sec, 2),
            waypoints=waypoints
        )
