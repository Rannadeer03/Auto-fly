"""AnomalyBuilder — Converts a CompletedTrack into a mature Anomaly.

Centralizes the heuristics for Severity and Confidence scoring.
"""

import math
import time
import uuid
from typing import Optional

from config import settings
from vegetation.anomaly import Anomaly, AnomalyStatus
from vegetation.mission_session_context import CompletedTrack


class AnomalyBuilder:
    """Builder to create a deterministic Anomaly from a CompletedTrack."""
    
    @staticmethod
    def build(ct: CompletedTrack) -> Optional[Anomaly]:
        """Convert a CompletedTrack into an Anomaly.
        
        Returns None if the track lacks a BestObservation or ProjectionResult
        (which implies it was lost immediately without yielding an observation).
        """
        if ct.best_observation is None or ct.projection is None:
            return None
            
        # ── Severity Model ───────────────────────────────────────────────────
        # Uses configurable heuristics (mean_vari and pixel_area)
        # Higher VARI and larger area => higher severity.
        norm_vari = min(1.0, max(0.0, ct.mean_vari))
        norm_area = min(1.0, ct.pixel_area / settings.ANOMALY_SEVERITY_BASE_AREA_PX)
        
        severity = (
            norm_vari * settings.ANOMALY_SEVERITY_WEIGHT_VARI +
            norm_area * settings.ANOMALY_SEVERITY_WEIGHT_AREA
        )
        severity = min(1.0, max(0.0, severity))
        
        # ── Confidence Model ─────────────────────────────────────────────────
        # Uses frames_visible, distance_from_center, and projection error.
        conf_frames = min(1.0, ct.frames_visible / settings.ANOMALY_CONF_MAX_FRAMES)
        
        dist = ct.best_observation.distance_from_image_center
        conf_dist = max(0.0, 1.0 - (dist / settings.ANOMALY_CONF_MAX_DIST_PX))
        
        err = ct.projection.estimated_error_m
        conf_err = max(0.0, 1.0 - (err / settings.ANOMALY_CONF_MAX_PROJ_ERR_M))
        
        confidence = (
            conf_frames * settings.ANOMALY_CONF_WEIGHT_FRAMES +
            conf_dist * settings.ANOMALY_CONF_WEIGHT_DIST +
            conf_err * settings.ANOMALY_CONF_WEIGHT_PROJ_ERR
        )
        confidence = min(1.0, max(0.0, confidence))
        
        # ── Ground Area Estimate ─────────────────────────────────────────────
        alt = ct.best_observation.altitude
        w, h = ct.best_observation.camera_resolution
        hfov, vfov = ct.best_observation.camera_fov
        
        ground_area = 0.0
        if w > 0 and h > 0 and alt > 0:
            gsd_x = (2.0 * alt * math.tan(math.radians(hfov / 2.0))) / float(w)
            gsd_y = (2.0 * alt * math.tan(math.radians(vfov / 2.0))) / float(h)
            ground_area = ct.pixel_area * (gsd_x * gsd_y)
            
        # Ensure a stable anomaly ID based on the track ID.
        anomaly_id = f"anom-{ct.track_id}"
        
        now = time.time()
        
        return Anomaly(
            anomaly_id=anomaly_id,
            track_id=ct.track_id,
            created_at=now,
            updated_at=now,
            status=AnomalyStatus.NEW,
            severity=round(severity, 4),
            confidence=round(confidence, 4),
            best_observation=ct.best_observation,
            projection_result=ct.projection,
            frames_visible=ct.frames_visible,
            history_length=ct.history_length,
            mean_vari=ct.mean_vari,
            max_vari=ct.max_vari,
            average_vari=ct.average_vari,
            pixel_area=ct.pixel_area,
            ground_area_estimate_m2=round(ground_area, 2)
        )
