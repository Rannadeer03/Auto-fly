"""Mission Session Context.

The single runtime object describing one active mission automation session
— owned and mutated only by services/mission_runner.py. Every future service
that needs to know "which mission is this", "where do its files live", or
"how far along is it" reads this context instead of re-deriving mission
folders, filenames, or progress calculations of its own.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class MissionSessionContext:
    """Runtime state for exactly one mission session, start to finish."""

    mission_id: str
    mission_name: str
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    mission_start_time: Optional[str] = None
    mission_end_time: Optional[str] = None

    # idle -> disabled|recording|failed -> stopped
    recording_state: str = "idle"

    video_file_path: Optional[Path] = None
    telemetry_log_path: Optional[Path] = None

    mission_statistics: dict = field(default_factory=dict)

    current_waypoint: int = 0
    mission_progress: float = 0.0

    def as_dict(self) -> dict:
        """JSON-serialisable snapshot, for status endpoints/logging."""
        return {
            "mission_id": self.mission_id,
            "session_id": self.session_id,
            "mission_name": self.mission_name,
            "mission_start_time": self.mission_start_time,
            "mission_end_time": self.mission_end_time,
            "recording_state": self.recording_state,
            "video_file_path": str(self.video_file_path) if self.video_file_path else None,
            "telemetry_log_path": (
                str(self.telemetry_log_path) if self.telemetry_log_path else None
            ),
            "mission_statistics": self.mission_statistics,
            "current_waypoint": self.current_waypoint,
            "mission_progress": self.mission_progress,
        }
