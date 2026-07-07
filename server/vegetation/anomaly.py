"""Anomaly domain model.

Represents a confirmed vegetation anomaly detected during a mission.
Provides a passive dataclass to store the anomaly attributes.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from vegetation.best_observation import BestObservation
from vegetation.projection_result import ProjectionResult


class AnomalyStatus(str, Enum):
    """Lifecycle status of a detected anomaly."""
    NEW = "NEW"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


@dataclass
class Anomaly:
    """A detected vegetation anomaly based on tracking history.

    This is a purely passive dataclass. It contains no persistence, AI,
    or business logic. All attributes must be provided at construction.
    """
    
    anomaly_id: str
    track_id: str
    created_at: float
    updated_at: float
    status: AnomalyStatus
    
    severity: float                      # 0.0 to 1.0 heuristic score
    confidence: float                    # 0.0 to 1.0 based on projection quality
    
    best_observation: BestObservation
    projection_result: ProjectionResult
    
    frames_visible: int
    history_length: int
    
    mean_vari: float                     # VARI from best_observation
    max_vari: float                      # Highest VARI observed across history
    average_vari: float                  # Average VARI across the tracked history
    
    pixel_area: float                    # Best observation area in pixels
    ground_area_estimate_m2: float       # Physical size estimate using GSD
