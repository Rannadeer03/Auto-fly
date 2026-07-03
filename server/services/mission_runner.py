"""Mission automation runner.

Coordinates the camera and storage services with MAVLink mission execution:

  • When a mission starts (POST /start succeeds) a mission session begins:
      - an isolated mission folder is created (missions/mission_<timestamp>/)
      - video recording starts automatically (if RECORDING_ENABLED)
      - the executed flight plan is saved as mission.json
      - a per-mission log file starts (logs/mission.log)
  • During the mission the drone flies normally — it is NEVER paused.
    A monitor thread continuously captures photos for mapping, either every
    PHOTO_DISTANCE_M metres of travel or every PHOTO_INTERVAL_S seconds
    (PHOTO_CAPTURE_MODE), geotagging each photo from live telemetry into
    mapping/photos.json. Telemetry is sampled into telemetry.json.
  • When the mission finishes (vehicle disarms, or connection is lost),
    recording stops and telemetry.json / mapping/photos.json / metadata.json
    are written.

Every camera/storage failure is contained: a failed photo never aborts the
mission.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from config import settings
from mavlink.connection import drone_state
from parser.waypoint_parser import haversine_m
from services.camera_service import camera_service
from services.recording_service import recording_service
from services.storage_service import MissionStorage, storage_service, utc_now_iso

logger = logging.getLogger(__name__)

_MONITOR_POLL_S = 0.2


class MissionRunner:
    """Owns the lifecycle of one active mission session at a time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._storage: Optional[MissionStorage] = None
        self._mission_name: str = ""
        self._started_at: Optional[str] = None
        self._photos_captured = 0
        self._end_reason: str = ""
        self._log_handler: Optional[logging.Handler] = None
        self._last_completed: Optional[str] = None  # folder name of last finished session

    # ── Public API ─────────────────────────────────────────────────────────────

    def on_mission_started(self, mission_name: str = "", mission_dict: Optional[dict] = None) -> None:
        """Begin a mission session. Called right after AUTO mode is confirmed."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                logger.warning("Mission session already active — ignoring new start.")
                return

            self._mission_name = mission_name
            self._storage = storage_service.create_mission_storage()
            self._started_at = utc_now_iso()
            self._photos_captured = 0
            self._end_reason = ""

            self._attach_mission_log(self._storage)

            try:
                self._storage.write_mission(mission_dict)
            except Exception:
                logger.exception("Failed to write mission.json")

            if settings.RECORDING_ENABLED:
                if not recording_service.start(self._storage.video_path):
                    logger.warning("Recording did not start for mission session.")
            else:
                logger.info("Recording disabled by configuration (RECORDING_ENABLED=0).")

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._monitor, name="mission-runner", daemon=True
            )
            self._thread.start()

        logger.info(
            "Mission session started: %s (folder=%s, capture=%s)",
            mission_name or "<unnamed>", self._storage.name,
            f"{settings.PHOTO_CAPTURE_MODE} "
            + (f"{settings.PHOTO_DISTANCE_M}m" if settings.PHOTO_CAPTURE_MODE == "distance"
               else f"{settings.PHOTO_INTERVAL_S}s"),
        )

    def stop_session(self, reason: str = "manual stop") -> bool:
        """Force-end the active session (recording stops, files are written)."""
        with self._lock:
            thread = self._thread
        if thread is None or not thread.is_alive():
            return False
        self._end_reason = reason
        self._stop_event.set()
        thread.join(timeout=10.0)
        return True

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def get_status(self) -> dict:
        with self._lock:
            active = self._thread is not None and self._thread.is_alive()
            return {
                "active": active,
                "mission_folder": self._storage.name if active and self._storage else None,
                "started_at": self._started_at if active else None,
                "photos_captured": self._photos_captured if active else 0,
                "recording": recording_service.is_recording,
                "capture_mode": settings.PHOTO_CAPTURE_MODE,
                "last_completed": self._last_completed,
            }

    # ── Monitor thread ─────────────────────────────────────────────────────────

    def _monitor(self) -> None:
        storage = self._storage
        last_telemetry_ts = 0.0
        was_armed = drone_state.armed
        arm_grace_deadline = time.monotonic() + 30.0  # allow start before arming settles

        # Continuous-capture state
        last_photo_ts = 0.0
        last_photo_pos: Optional[tuple[float, float]] = None

        try:
            while not self._stop_event.is_set():
                now = time.monotonic()

                # ── Telemetry sampling ─────────────────────────────────────────
                if now - last_telemetry_ts >= settings.TELEMETRY_LOG_INTERVAL_S:
                    last_telemetry_ts = now
                    sample = drone_state.snapshot()
                    sample["timestamp"] = utc_now_iso()
                    storage.append_telemetry(sample)

                # ── Continuous photo capture (never pauses the drone) ──────────
                if self._should_capture(now, last_photo_ts, last_photo_pos):
                    if self._capture_photo(storage):
                        last_photo_ts = now
                        if drone_state.latitude or drone_state.longitude:
                            last_photo_pos = (drone_state.latitude, drone_state.longitude)

                # ── Completion detection ───────────────────────────────────────
                if drone_state.armed:
                    was_armed = True
                if was_armed and not drone_state.armed:
                    self._end_reason = "vehicle disarmed (mission finished)"
                    break
                if not was_armed and now > arm_grace_deadline:
                    self._end_reason = "vehicle never armed within grace period"
                    break
                if not drone_state.connected:
                    self._end_reason = "MAVLink connection lost"
                    break

                self._stop_event.wait(_MONITOR_POLL_S)
        except Exception:
            logger.exception("Mission monitor crashed")
            self._end_reason = self._end_reason or "monitor error"
        finally:
            self._finalise(storage)

    def _should_capture(
        self,
        now: float,
        last_photo_ts: float,
        last_photo_pos: Optional[tuple[float, float]],
    ) -> bool:
        if settings.CAPTURE_ONLY_IN_AUTO:
            if not drone_state.armed or drone_state.flight_mode.upper() != "AUTO":
                return False

        if settings.PHOTO_CAPTURE_MODE == "time":
            return now - last_photo_ts >= settings.PHOTO_INTERVAL_S

        # Distance mode: capture when the drone has moved PHOTO_DISTANCE_M
        # since the last photo. Falls back to first-fix capture once a GPS
        # position exists.
        lat, lon = drone_state.latitude, drone_state.longitude
        if lat == 0.0 and lon == 0.0:
            return False
        if last_photo_pos is None:
            return True
        moved = haversine_m(last_photo_pos[0], last_photo_pos[1], lat, lon)
        return moved >= settings.PHOTO_DISTANCE_M

    def _capture_photo(self, storage: MissionStorage) -> bool:
        try:
            path = storage.next_photo_path(self._photos_captured + 1)
            if camera_service.capture_photo(path):
                storage.record_photo(path, drone_state.snapshot())
                self._photos_captured += 1
                return True
        except Exception:
            logger.exception("Continuous photo capture failed")
        return False

    # ── Per-mission log file ───────────────────────────────────────────────────

    def _attach_mission_log(self, storage: MissionStorage) -> None:
        try:
            handler = logging.FileHandler(storage.log_path, encoding="utf-8")
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            logging.getLogger().addHandler(handler)
            self._log_handler = handler
        except Exception:
            logger.exception("Failed to attach mission log file")
            self._log_handler = None

    def _detach_mission_log(self) -> None:
        if self._log_handler is not None:
            logging.getLogger().removeHandler(self._log_handler)
            try:
                self._log_handler.close()
            except Exception:
                pass
            self._log_handler = None

    # ── Finalisation ───────────────────────────────────────────────────────────

    def _finalise(self, storage: MissionStorage) -> None:
        reason = self._end_reason or "unknown"
        logger.info("Mission session ending: %s", reason)

        try:
            recording_service.stop()
        except Exception:
            logger.exception("Failed to stop recording")

        try:
            storage.flush()
        except Exception:
            logger.exception("Failed to write telemetry.json / mapping/photos.json")

        try:
            storage.write_metadata(
                {
                    "mission_name": self._mission_name,
                    "folder": storage.name,
                    "started_at": self._started_at,
                    "ended_at": utc_now_iso(),
                    "end_reason": reason,
                    "waypoints_total": drone_state.waypoint_count,
                    "photos_captured": self._photos_captured,
                    "video_file": storage.video_path.name if storage.video_path.exists() else None,
                    "capture_mode": settings.PHOTO_CAPTURE_MODE,
                    "photo_distance_m": settings.PHOTO_DISTANCE_M,
                    "photo_interval_s": settings.PHOTO_INTERVAL_S,
                    "recording_enabled": settings.RECORDING_ENABLED,
                }
            )
        except Exception:
            logger.exception("Failed to write metadata.json")

        logger.info(
            "Mission session complete: %s (%d photos)",
            storage.name, self._photos_captured,
        )
        self._detach_mission_log()

        # Index the finished mission folder (after the mission log is closed)
        # so the web UI can browse, search and download it without any
        # filesystem access.
        try:
            storage_service.build_index(storage.root)
        except Exception:
            logger.exception("Failed to build mission index")
        with self._lock:
            self._last_completed = storage.name


# Module-level singleton
mission_runner = MissionRunner()
