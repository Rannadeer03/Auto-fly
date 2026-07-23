"""Capture strategies for mission photo automation.

Two interchangeable strategies decide when the Pi should trigger a photo
during an active survey mission. MissionRunner is strategy-agnostic — it
just calls tick() every monitor cycle — so switching CAPTURE_STRATEGY in
config.py (or per-request via GridRequest.capture_mode) is the only change
needed to swap behaviour; no other code touches the decision logic.
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from abc import ABC, abstractmethod
from typing import Optional

from config import settings
from mavlink.connection import drone_state
from parser.waypoint_parser import haversine_m
from services.camera_service import camera_service
from services.exif_service import embed_exif
from services.image_quality import score_frame
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

    def _select_best_frame(self):
        """Grab up to (1 + CAPTURE_RETRY_LIMIT) frames, scoring each with
        image_quality.score_frame, and return the sharpest one — stopping
        early the moment one clears the quality threshold. Each retry waits
        briefly for a genuinely new published frame rather than rescoring
        the same one."""
        best_frame = None
        best_score = None
        last_ts = None
        for _ in range(settings.CAPTURE_RETRY_LIMIT + 1):
            frame, ts = camera_service.get_frame_with_ts()
            if frame is None:
                continue
            if ts == last_ts:
                time.sleep(0.05)
                frame, ts = camera_service.get_frame_with_ts()
                if frame is None:
                    continue
            last_ts = ts
            score = score_frame(frame)
            if best_score is None or score.confidence > best_score.confidence:
                best_frame, best_score = frame, score
            if score.passed:
                break
        return best_frame, best_score

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

            frame, quality = self._select_best_frame()
            if frame is None:
                self.failed_captures += 1
                logger.error(
                    "Capture failed at waypoint %d: no camera frame available "
                    "(%d failed capture(s) so far this mission).",
                    waypoint_number, self.failed_captures,
                )
                return False
            if quality is not None and not quality.passed:
                logger.warning(
                    "Waypoint %d: best of %d attempt(s) still below quality threshold "
                    "(confidence=%.3f) — keeping it anyway rather than skipping the shot.",
                    waypoint_number, settings.CAPTURE_RETRY_LIMIT + 1, quality.confidence,
                )

            if not camera_service.write_frame(frame, path, thumb_path=thumb_path):
                self.failed_captures += 1
                logger.error(
                    "Capture failed at waypoint %d: write to disk failed "
                    "(%d failed capture(s) so far this mission).",
                    waypoint_number, self.failed_captures,
                )
                return False

            # checksum is filled in after EXIF embedding below — embedding
            # rewrites the file's bytes, and a checksum has to describe the
            # file as it will actually sit on disk (a file can't carry a
            # hash of itself, so the EXIF UserComment's copy of this field
            # is necessarily blank; metadata.json/csv hold the real one).
            record = storage.record_photo(
                path,
                drone_state.snapshot(),
                waypoint_number=waypoint_number,
                capture_sequence=capture_sequence,
                camera_orientation_deg=settings.CAMERA_PITCH_DEG,
                image_id=str(uuid.uuid4()),
                quality=quality.as_dict() if quality is not None else None,
                checksum_sha256="",
            )
            height, width = frame.shape[:2]
            embed_exif(path, record, width, height)
            record["checksum_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()

            self.photos_captured += 1
            return True
        except Exception:
            self.failed_captures += 1
            logger.exception("Unexpected error during capture at waypoint %d", waypoint_number)
            return False


class HoverCaptureStrategy(CaptureStrategy):
    """Waypoint -> Loiter -> Confirm tolerance -> Capture one photo -> Continue.

    Every capture point is followed by a dedicated MAV_CMD_NAV_LOITER_TIME
    mission item (see mission_enrichment.py) — a standard ArduPilot command
    that ArduCopter only reports MISSION_ITEM_REACHED for once its hold
    duration has actually elapsed, so the vehicle is already loitering by
    the time this strategy sees that item's seq. This strategy then
    independently confirms the vehicle is within position/altitude
    tolerance of the planned point and that the airframe is actually stable
    (ground speed and all three angular rates below threshold) before
    firing the shutter — not just trusting a fixed delay — so a gust of
    wind or a slow-to-settle gimbal-less mount doesn't blur the shot. A
    bounded max-wait guarantees the mission never stalls if that's never
    cleanly confirmed (e.g. a noisy sensor on a breezy day).
    """

    # Absolute floor: always let the arrival transient decay a little before
    # even checking telemetry, regardless of how "ready" it reports.
    _MIN_SETTLE_S = 0.2
    # Ceiling: capture anyway once this much time has passed at the
    # waypoint, whether or not readiness was ever confirmed. This is what
    # keeps a mission from stalling forever on a bad IMU reading or wind.
    _MAX_WAIT_S = 3.0
    # "Stable" thresholds — comfortably tighter than normal AUTO-mode loiter
    # tolerances, loose enough that ordinary sensor noise doesn't block them.
    _STABLE_GROUND_SPEED_MS = 0.3
    _STABLE_ANGULAR_RATE_DPS = 5.0

    def __init__(self, capture_points: dict[int, tuple[float, float, float]]) -> None:
        super().__init__()
        self._capture_points = capture_points  # seq -> (lat, lon, altitude_rel)
        self._captured_seqs: set[int] = set()
        self._pending_seq: Optional[int] = None
        self._pending_since: float = 0.0
        self._warned_unready = False

    def _is_stable(self) -> bool:
        s = drone_state
        return (
            s.ground_speed < self._STABLE_GROUND_SPEED_MS
            and abs(s.roll_speed) < self._STABLE_ANGULAR_RATE_DPS
            and abs(s.pitch_speed) < self._STABLE_ANGULAR_RATE_DPS
            and abs(s.yaw_speed) < self._STABLE_ANGULAR_RATE_DPS
        )

    def _is_in_tolerance(self, seq: int) -> bool:
        """Confirm the vehicle is actually at the planned position/altitude
        for *seq* — belt-and-suspenders alongside ArduPilot's own
        acceptance-radius/MISSION_ITEM_REACHED behaviour."""
        target = self._capture_points.get(seq)
        if target is None:
            return True
        lat, lon, alt = target
        s = drone_state
        within_radius = haversine_m(s.latitude, s.longitude, lat, lon) <= settings.WAYPOINT_RADIUS_M
        within_altitude = abs(s.altitude_rel - alt) <= settings.ALTITUDE_TOLERANCE_M
        return within_radius and within_altitude

    def tick(self, now: float, storage: MissionStorage) -> bool:
        if not self._capture_allowed():
            return False

        seq = drone_state.last_reached_waypoint
        if (
            seq in self._capture_points
            and seq not in self._captured_seqs
            and self._pending_seq != seq
        ):
            self._pending_seq = seq
            self._pending_since = now
            self._warned_unready = False
            logger.debug("Hover capture armed for waypoint %d.", seq)

        if self._pending_seq is None:
            return False

        elapsed = now - self._pending_since
        if elapsed < self._MIN_SETTLE_S:
            return False

        ready = self._is_stable() and self._is_in_tolerance(self._pending_seq)
        if elapsed < self._MAX_WAIT_S and not ready:
            return False  # not yet in position/stable — keep waiting

        target_seq = self._pending_seq
        if not ready and not self._warned_unready:
            self._warned_unready = True
            logger.warning(
                "Waypoint %d: position/altitude/stability never confirmed within "
                "%.1fs — capturing anyway to avoid stalling the mission.",
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

    In hover mode, capture points (seq -> planned lat/lon/altitude) come
    from the executed mission's is_capture_point flags — set by
    mission_enrichment.py on the MAV_CMD_NAV_LOITER_TIME item it inserts
    after every capture waypoint. A mission with none (e.g. a raw QGC file
    uploaded with CAPTURE_STRATEGY=continuous) simply never fires.
    """
    if settings.CAPTURE_STRATEGY == "continuous":
        return ContinuousCaptureStrategy()

    capture_points: dict[int, tuple[float, float, float]] = {}
    if mission_dict:
        capture_points = {
            wp["index"]: (wp["latitude"], wp["longitude"], wp["altitude"])
            for wp in mission_dict.get("waypoints", [])
            if wp.get("is_capture_point")
        }
    return HoverCaptureStrategy(capture_points)
