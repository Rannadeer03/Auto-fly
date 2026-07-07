"""Frame Synchronizer.

Associates one telemetry snapshot with one camera-frame event. This is a
metadata-only foundation: no frame is ever read, decoded, or processed here.
Future phases (VARI, anomaly detection) will call sync() once per frame they
pull from the camera pipeline instead of re-reading drone_state themselves —
that keeps every synchronized record consistent with the owning mission
session (services/mission_session.py) and means no other service needs its
own notion of "current telemetry for this frame".
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Optional

from mavlink.connection import drone_state
from services.mission_session import MissionSessionContext
from services.storage_service import utc_now_iso

logger = logging.getLogger(__name__)


@dataclass
class SyncedFrameMetadata:
    """Telemetry synchronized to a single camera frame — metadata only."""

    timestamp: str
    latitude: float
    longitude: float
    altitude_rel: float
    altitude_msl: float
    heading: int
    ground_speed: float
    current_waypoint: int
    mission_progress: float


class FrameSynchronizer:
    """Ties camera-frame timestamps to live telemetry for one mission session."""

    def __init__(self, session: MissionSessionContext) -> None:
        self._session = session
        self._lock = threading.Lock()
        self._samples: list[SyncedFrameMetadata] = []
        self._active = False

    def start(self) -> None:
        with self._lock:
            self._samples.clear()
            self._active = True
        logger.info(
            "Frame synchronizer started (session=%s, mission=%s).",
            self._session.session_id, self._session.mission_name,
        )

    def sync(self, timestamp: Optional[str] = None) -> Optional[SyncedFrameMetadata]:
        """Associate one camera-frame timestamp with the current telemetry
        snapshot. Call once per frame; returns None if not started/already
        stopped so a stray call from a shutting-down pipeline is harmless."""
        if not self._active:
            return None
        s = drone_state
        record = SyncedFrameMetadata(
            timestamp=timestamp or utc_now_iso(),
            latitude=s.latitude,
            longitude=s.longitude,
            altitude_rel=s.altitude_rel,
            altitude_msl=s.altitude_msl,
            heading=s.heading,
            ground_speed=s.ground_speed,
            current_waypoint=s.current_waypoint,
            mission_progress=self._session.mission_progress,
        )
        with self._lock:
            self._samples.append(record)
        return record

    def stop(self) -> list[SyncedFrameMetadata]:
        with self._lock:
            self._active = False
            samples = list(self._samples)
        logger.info(
            "Frame synchronizer stopped (session=%s, %d synced frame(s)).",
            self._session.session_id, len(samples),
        )
        return samples

    @property
    def sample_count(self) -> int:
        with self._lock:
            return len(self._samples)
