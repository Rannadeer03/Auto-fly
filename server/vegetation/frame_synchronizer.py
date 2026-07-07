"""FrameSynchronizer — bridges CameraService + DroneState into SynchronizedFrame.

Architecture
------------
The synchronizer is *poll-driven*, not thread-driven.  Callers (the
VegetationPipeline) invoke `poll()` on each iteration of their own loop.
`poll()` reads the latest frame from CameraService and the latest telemetry
snapshot from DroneState, stamps both with a UUID and monotonic clock, and
returns a `SynchronizedFrame` when a *new* frame is available (i.e., the frame
pointer changed since the last poll).

This design keeps the synchronizer free of its own background thread, making it
trivially testable and ensuring it cannot outlive its caller.

Frame skipping
--------------
`VARI_PROCESS_EVERY_N` controls how many camera frames are skipped between
processed frames.  The frame number counter always increments by 1 per *new*
camera frame seen, regardless of whether it is processed.  Only frames whose
counter is divisible by VARI_PROCESS_EVERY_N are returned from `poll()`.

Session reset
-------------
Calling `reset()` sets frame_number back to 0.  Call this when a new mission
session starts so that frame numbers restart from zero per session.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

import numpy as np

from config import settings
from mavlink.connection import drone_state
from services.camera_service import camera_service
from vegetation.synchronized_frame import SynchronizedFrame

logger = logging.getLogger(__name__)


class FrameSynchronizer:
    """Merges camera frames with drone telemetry into SynchronizedFrame objects.

    Thread-safety: `poll()` is NOT thread-safe.  Call it from a single thread
    (the VegetationPipeline's processing loop).  The underlying CameraService
    and DroneState are themselves thread-safe; the synchronizer only adds its
    own lightweight non-shared state.
    """

    def __init__(self) -> None:
        self._frame_number: int = 0
        self._last_frame_id: Optional[int] = None  # id() of the last seen ndarray

    # ── Public API ─────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset frame counter.  Call at the start of each mission session."""
        self._frame_number = 0
        self._last_frame_id = None
        logger.debug("FrameSynchronizer reset: frame_number = 0")

    def poll(self) -> Optional[SynchronizedFrame]:
        """Return a SynchronizedFrame if a new camera frame is available.

        Returns None if:
        - No frame has been captured by CameraService yet.
        - The frame has not changed since the last call (same frame, no skip).
        - The current frame_number is not divisible by VARI_PROCESS_EVERY_N.
        """
        raw_frame: Optional[np.ndarray] = camera_service.get_frame()
        if raw_frame is None:
            return None

        # Detect a new frame by pointer identity — cv2.read() always returns a
        # freshly allocated ndarray, so id() changes on every new capture.
        frame_id = id(raw_frame)
        if frame_id == self._last_frame_id:
            return None  # Camera hasn't delivered a new frame yet

        self._last_frame_id = frame_id
        self._frame_number += 1

        # Apply frame-skip policy
        if self._frame_number % settings.VARI_PROCESS_EVERY_N != 0:
            return None

        # Snapshot telemetry atomically
        state = drone_state.snapshot()

        # Compute mission progress fraction safely
        total_wp = state.get("waypoint_count", 0)
        current_wp = state.get("current_waypoint", 0)
        if total_wp > 0:
            mission_progress = round(current_wp / total_wp, 4)
        else:
            mission_progress = 0.0

        return SynchronizedFrame(
            frame_uuid=str(uuid.uuid4()),
            frame_number=self._frame_number,
            timestamp=time.monotonic(),
            image=raw_frame.copy(),  # defensive copy — caller may process async
            lat=state.get("latitude", 0.0),
            lon=state.get("longitude", 0.0),
            alt=state.get("altitude_rel", 0.0),
            heading=float(state.get("heading", 0)),
            yaw=state.get("yaw", 0.0),
            ground_speed=state.get("ground_speed", 0.0),
            mission_progress=mission_progress,
            waypoint=state.get("current_waypoint", 0),
        )

    @property
    def frame_number(self) -> int:
        """Total camera frames seen so far (includes skipped frames)."""
        return self._frame_number
