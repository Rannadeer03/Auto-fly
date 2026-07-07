"""Mission automation runner.

Coordinates the camera and storage services with MAVLink mission execution:

  • When a mission starts (POST /start succeeds) a mission session begins:
      - an isolated mission folder is created: missions/<Mission_Name>_<timestamp>/
      - video recording starts automatically (if RECORDING_ENABLED)
      - the executed flight plan is saved as mission.json
      - a per-mission log file starts (logs/mission.log)
  • A monitor thread drives photo capture via a pluggable CaptureStrategy
    (services/capture_strategies.py). By default (CAPTURE_STRATEGY="hover")
    each survey waypoint holds position until the vehicle is confirmed
    stable (or a bounded max-wait elapses), then exactly one photo is taken.
    Every captured photo's full metadata (position, attitude, waypoint,
    GPS fix, etc.) is accumulated in memory during the flight.
  • When the mission finishes (vehicle disarms, or connection is lost),
    recording stops and telemetry.json / metadata.json / metadata.csv are
    written.
  • Alongside the above, a MissionSessionContext (services/mission_session.py)
    is created for the session and a FrameSynchronizer (services/
    frame_synchronizer.py) is started — the runtime foundation other phases
    read from instead of building their own mission folders or telemetry
    lookups. If VARI_ENABLED, a VariPipelineWorker (services/
    vari_pipeline.py) also starts on its own paced background thread,
    writing a vegetation-overlay video alongside the original recording —
    it can never delay flight operations; a slow frame is simply dropped.

Every camera/storage failure is contained: a failed photo never aborts the
mission.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from config import settings
from mavlink.connection import drone_state
from services.camera_service import camera_service
from services.capture_strategies import CaptureStrategy, build_capture_strategy
from services.frame_synchronizer import FrameSynchronizer
from services.mission_session import MissionSessionContext
from services.recording_service import recording_service
from services.storage_service import MissionStorage, storage_service, utc_now_iso
from services.vari_pipeline import VariPipelineWorker

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
        self._strategy: Optional[CaptureStrategy] = None
        self._end_reason: str = ""
        self._log_handler: Optional[logging.Handler] = None
        self._last_completed: Optional[str] = None  # folder name of last finished session

        self._session: Optional[MissionSessionContext] = None
        self._frame_sync: Optional[FrameSynchronizer] = None
        self._vari_worker: Optional[VariPipelineWorker] = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def on_mission_started(self, mission_name: str = "", mission_dict: Optional[dict] = None) -> None:
        """Begin a mission session. Called right after AUTO mode is confirmed.

        *mission_name* is the mission's filename (e.g. "North_Field.plan" or
        an uploaded "survey.waypoints") — the extension is stripped to get
        the human-readable label used both in metadata and as the basis for
        the mission folder name (missions/<label>_<timestamp>/).
        """
        clean_name = Path(mission_name).stem if mission_name else ""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                logger.warning("Mission session already active — ignoring new start.")
                return

            self._mission_name = clean_name
            self._storage = storage_service.create_mission_storage(mission_name=clean_name)
            self._started_at = utc_now_iso()
            self._strategy = build_capture_strategy(mission_dict)
            self._end_reason = ""

            self._session = MissionSessionContext(
                mission_id=self._storage.mission_id,
                mission_name=clean_name or self._storage.mission_id,
                mission_start_time=self._started_at,
                video_file_path=self._storage.video_path,
                vari_video_file_path=self._storage.vari_video_path,
                telemetry_log_path=self._storage.telemetry_path,
                anomaly_db_path=self._storage.anomaly_db_path,
            )
            self._frame_sync = FrameSynchronizer(self._session)
            self._frame_sync.start()

            if settings.VARI_ENABLED:
                self._vari_worker = VariPipelineWorker(
                    camera=camera_service,
                    frame_sync=self._frame_sync,
                    output_path=self._storage.vari_video_path,
                    session=self._session,
                )
                self._vari_worker.start()
            else:
                self._vari_worker = None

            self._attach_mission_log(self._storage)

            try:
                self._storage.write_mission(mission_dict)
            except Exception:
                logger.exception("Failed to write mission.json")

            if settings.RECORDING_ENABLED:
                if recording_service.start(self._storage.video_path):
                    self._session.recording_state = "recording"
                else:
                    self._session.recording_state = "failed"
                    logger.warning("Recording did not start for mission session.")
            else:
                self._session.recording_state = "disabled"
                logger.info("Recording disabled by configuration (RECORDING_ENABLED=0).")

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._monitor, name="mission-runner", daemon=True
            )
            self._thread.start()

        logger.info(
            "Mission session started: %s (folder=%s, capture_strategy=%s)",
            clean_name or "<unnamed>", self._storage.name, settings.CAPTURE_STRATEGY,
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
            photos = self._strategy.photos_captured if active and self._strategy else 0
            failed = self._strategy.failed_captures if active and self._strategy else 0
            session = self._session
            return {
                "active": active,
                "mission_folder": self._storage.name if active and self._storage else None,
                "started_at": self._started_at if active else None,
                "photos_captured": photos,
                "failed_captures": failed,
                "recording": recording_service.is_recording,
                "capture_mode": settings.CAPTURE_STRATEGY,
                "last_completed": self._last_completed,
                "session_id": session.session_id if active and session else None,
                "current_waypoint": session.current_waypoint if active and session else 0,
                "mission_progress": session.mission_progress if active and session else 0.0,
            }

    def get_session_context(self) -> Optional[MissionSessionContext]:
        """Expose the active session context so other services (frame sync,
        future VARI/anomaly phases) can read paths/state without creating
        their own mission folders or filenames."""
        with self._lock:
            return self._session

    def get_frame_synchronizer(self) -> Optional[FrameSynchronizer]:
        """Expose the active frame synchronizer so a future frame-producing
        service (VARI, anomaly detection) can call sync() once per camera
        frame instead of building its own telemetry lookup."""
        with self._lock:
            return self._frame_sync

    def get_vari_worker(self) -> Optional[VariPipelineWorker]:
        """Expose the active VARI pipeline worker (e.g. for a future
        diagnostics surface) without any other service starting its own."""
        with self._lock:
            return self._vari_worker

    # ── Monitor thread ─────────────────────────────────────────────────────────

    def _monitor(self) -> None:
        storage = self._storage
        strategy = self._strategy
        last_telemetry_ts = 0.0
        was_armed = drone_state.armed
        arm_grace_deadline = time.monotonic() + 30.0  # allow start before arming settles

        try:
            while not self._stop_event.is_set():
                now = time.monotonic()

                # ── Telemetry sampling ─────────────────────────────────────────
                if now - last_telemetry_ts >= settings.TELEMETRY_LOG_INTERVAL_S:
                    last_telemetry_ts = now
                    sample = drone_state.snapshot()
                    sample["timestamp"] = utc_now_iso()
                    storage.append_telemetry(sample)

                # ── Photo capture (delegated to the active CaptureStrategy) ─────
                strategy.tick(now, storage)

                # ── Session progress (read by future frame-level phases) ────────
                if self._session is not None:
                    self._session.current_waypoint = drone_state.current_waypoint
                    total = drone_state.waypoint_count
                    self._session.mission_progress = round(
                        (drone_state.current_waypoint / total * 100) if total > 0 else 0.0, 1
                    )

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

        if self._session is not None:
            self._session.mission_end_time = utc_now_iso()
            if self._session.recording_state == "recording":
                self._session.recording_state = "stopped"

        try:
            if self._vari_worker is not None:
                self._vari_worker.stop()
        except Exception:
            logger.exception("Failed to stop VARI pipeline worker")

        try:
            frames = self._frame_sync.stop() if self._frame_sync else []
            storage.write_frame_sync([asdict(f) for f in frames])
        except Exception:
            logger.exception("Failed to write frame_sync.json")

        try:
            recording_service.stop()
        except Exception:
            logger.exception("Failed to stop recording")

        try:
            storage.flush()
        except Exception:
            logger.exception("Failed to write telemetry.json")

        photos_captured = self._strategy.photos_captured if self._strategy else 0
        failed_captures = self._strategy.failed_captures if self._strategy else 0
        try:
            storage.write_metadata(
                {
                    "mission_name": self._mission_name,
                    "folder": storage.name,
                    "started_at": self._started_at,
                    "ended_at": utc_now_iso(),
                    "end_reason": reason,
                    "waypoints_total": drone_state.waypoint_count,
                    "photos_captured": photos_captured,
                    "failed_captures": failed_captures,
                    "video_file": storage.video_path.name if storage.video_path.exists() else None,
                    "capture_mode": settings.CAPTURE_STRATEGY,
                    "hover_hold_time_s": settings.HOVER_HOLD_TIME_S,
                    "camera_orientation_deg": settings.CAMERA_PITCH_DEG,
                    "photo_distance_m": settings.PHOTO_DISTANCE_M,
                    "photo_interval_s": settings.PHOTO_INTERVAL_S,
                    "recording_enabled": settings.RECORDING_ENABLED,
                }
            )
        except Exception:
            logger.exception("Failed to write metadata.json")

        logger.info(
            "Mission session complete: %s (%d photos, %d failed captures)",
            storage.name, photos_captured, failed_captures,
        )
        self._detach_mission_log()

        # Index the finished mission folder (after the mission log is closed)
        # so the web UI can browse, search and download it without any
        # filesystem access.
        try:
            index = storage_service.build_index(storage.root)
            stats = index.get("stats") if index else None
            if self._session is not None and stats:
                self._session.mission_statistics = stats
                storage.write_statistics(stats)
        except Exception:
            logger.exception("Failed to build mission index")
        with self._lock:
            self._last_completed = storage.name
            self._session = None
            self._frame_sync = None
            self._vari_worker = None


# Module-level singleton
mission_runner = MissionRunner()
