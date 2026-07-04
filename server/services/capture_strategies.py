"""Capture strategies for mission photo automation.

Two interchangeable strategies decide when the Pi should trigger a photo
during an active survey mission. MissionRunner is strategy-agnostic — it
just calls tick() every monitor cycle — so switching CAPTURE_STRATEGY in
config.py (or per-request via GridRequest.capture_mode) is the only change
needed to swap behaviour; no other code touches the decision logic.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from config import settings
from mavlink.connection import drone_state
from parser.waypoint_parser import haversine_m
from services.camera_service import camera_service
from services.storage_service import MissionStorage

logger = logging.getLogger(__name__)


class CaptureStrategy(ABC):
    """Decides when to trigger a photo capture during an active mission."""

    def __init__(self) -> None:
        self.photos_captured = 0
        self.failed_captures = 0

    @abstractmethod
    def tick(self, now: float, storage: MissionStorage) -> bool:
        """Called once per monitor cycle. Returns True if a photo was captured."""

    def _capture_allowed(self) -> bool:
        if not settings.CAPTURE_ONLY_IN_AUTO:
            return True
        return drone_state.armed and drone_state.flight_mode.upper() == "AUTO"

    def _capture_one(self, storage: MissionStorage, waypoint_number: int) -> bool:
        """Take one photo, verify it saved, and record its full metadata.

        Returns False (and logs, never raises) on any failure — a bad shot
        must never abort the mission. Nothing is marked "captured" by the
        caller unless this returns True, so a failure is safe to retry.
        """
        try:
            capture_sequence = self.photos_captured + 1
            path = storage.next_photo_path(capture_sequence)
            thumb_path = storage.thumb_path_for(path)
            if not camera_service.capture_photo(path, thumb_path=thumb_path):
                self.failed_captures += 1
                logger.error(
                    "Capture failed at waypoint %d (%d failed capture(s) so far this mission).",
                    waypoint_number, self.failed_captures,
                )
                return False

            storage.record_photo(
                path,
                drone_state.snapshot(),
                waypoint_number=waypoint_number,
                capture_sequence=capture_sequence,
                camera_orientation_deg=settings.CAMERA_PITCH_DEG,
            )
            self.photos_captured += 1
            return True
        except Exception:
            self.failed_captures += 1
            logger.exception("Unexpected error during capture at waypoint %d", waypoint_number)
            return False


class HoverCaptureStrategy(CaptureStrategy):
    """Waypoint -> Position Hold -> Capture one photo -> Continue (default).

    ArduCopter performs the hold itself: every survey waypoint carries a
    MAV_CMD_NAV_WAYPOINT param1 hold time (see grid_planner.py), so the
    vehicle is already loitering once MISSION_ITEM_REACHED fires for that
    seq. This strategy then confirms the airframe is actually stable
    (ground speed and all three angular rates below threshold) before
    firing the shutter — not just a fixed delay — so a gust of wind or a
    slow-to-settle gimbal-less mount doesn't blur the shot. A bounded
    max-wait guarantees the mission never stalls if stability is never
    cleanly detected (e.g. a noisy sensor on a breezy day).
    """

    # Absolute floor: always let the arrival transient decay a little before
    # even checking telemetry, regardless of how "stable" it reports.
    _MIN_SETTLE_S = 0.2
    # Ceiling: capture anyway once this much time has passed at the
    # waypoint, whether or not stability was ever confirmed. This is what
    # keeps a mission from stalling forever on a bad IMU reading or wind.
    _MAX_WAIT_S = 3.0
    # "Stable" thresholds — comfortably tighter than normal AUTO-mode loiter
    # tolerances, loose enough that ordinary sensor noise doesn't block them.
    _STABLE_GROUND_SPEED_MS = 0.3
    _STABLE_ANGULAR_RATE_DPS = 5.0

    def __init__(self, capture_waypoint_seqs: set[int]) -> None:
        super().__init__()
        self._capture_seqs = capture_waypoint_seqs
        self._captured_seqs: set[int] = set()
        self._pending_seq: Optional[int] = None
        self._pending_since: float = 0.0
        self._warned_unstable = False

    def _is_stable(self) -> bool:
        s = drone_state
        return (
            s.ground_speed < self._STABLE_GROUND_SPEED_MS
            and abs(s.roll_speed) < self._STABLE_ANGULAR_RATE_DPS
            and abs(s.pitch_speed) < self._STABLE_ANGULAR_RATE_DPS
            and abs(s.yaw_speed) < self._STABLE_ANGULAR_RATE_DPS
        )

    def tick(self, now: float, storage: MissionStorage) -> bool:
        if not self._capture_allowed():
            return False

        seq = drone_state.last_reached_waypoint
        if (
            seq in self._capture_seqs
            and seq not in self._captured_seqs
            and self._pending_seq != seq
        ):
            self._pending_seq = seq
            self._pending_since = now
            self._warned_unstable = False
            logger.debug("Hover capture armed for waypoint %d.", seq)

        if self._pending_seq is None:
            return False

        elapsed = now - self._pending_since
        if elapsed < self._MIN_SETTLE_S:
            return False

        stable = self._is_stable()
        if elapsed < self._MAX_WAIT_S and not stable:
            return False  # still moving/rotating — keep waiting for stability

        target_seq = self._pending_seq
        if not stable and not self._warned_unstable:
            self._warned_unstable = True
            logger.warning(
                "Waypoint %d: stability never confirmed within %.1fs — capturing anyway "
                "to avoid stalling the mission.",
                target_seq, self._MAX_WAIT_S,
            )

        if self._capture_one(storage, waypoint_number=target_seq):
            self._captured_seqs.add(target_seq)
            self._pending_seq = None
            logger.info("Hover capture: photo taken at waypoint %d.", target_seq)
            return True

        # Capture failed — leave _pending_seq alone (don't clear it) so the
        # next tick retries immediately, as long as the vehicle is still at
        # this same waypoint. Once the mission moves past it, seq changes
        # and this waypoint's shot is permanently missed (logged above),
        # rather than blocking the rest of the survey.
        return False


class ContinuousCaptureStrategy(CaptureStrategy):
    """Drone never stops; photos are triggered by distance or time while
    flying. Reserved for future use — not the default, but kept alongside
    HoverCaptureStrategy so it can be enabled with a single settings change."""

    def __init__(self) -> None:
        super().__init__()
        self._last_photo_ts: float = 0.0
        self._last_photo_pos: Optional[tuple[float, float]] = None

    def tick(self, now: float, storage: MissionStorage) -> bool:
        if not self._capture_allowed():
            return False
        if not self._should_capture(now):
            return False
        if self._capture_one(storage, waypoint_number=drone_state.current_waypoint):
            self._last_photo_ts = now
            if drone_state.latitude or drone_state.longitude:
                self._last_photo_pos = (drone_state.latitude, drone_state.longitude)
            return True
        return False

    def _should_capture(self, now: float) -> bool:
        if settings.PHOTO_CAPTURE_MODE == "time":
            return now - self._last_photo_ts >= settings.PHOTO_INTERVAL_S

        lat, lon = drone_state.latitude, drone_state.longitude
        if lat == 0.0 and lon == 0.0:
            return False
        if self._last_photo_pos is None:
            return True
        moved = haversine_m(self._last_photo_pos[0], self._last_photo_pos[1], lat, lon)
        return moved >= settings.PHOTO_DISTANCE_M


def build_capture_strategy(mission_dict: Optional[dict]) -> CaptureStrategy:
    """Construct the strategy configured by settings.CAPTURE_STRATEGY.

    In hover mode, capture waypoint indices come from the executed mission's
    is_capture_point flags (set by grid_planner.py); a mission with none
    (e.g. a raw QGC file uploaded for debugging) simply never fires.
    """
    if settings.CAPTURE_STRATEGY == "continuous":
        return ContinuousCaptureStrategy()

    capture_seqs: set[int] = set()
    if mission_dict:
        capture_seqs = {
            wp["index"] for wp in mission_dict.get("waypoints", [])
            if wp.get("is_capture_point")
        }
    return HoverCaptureStrategy(capture_seqs)
