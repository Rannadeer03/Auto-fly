"""Mission automation runner.

Coordinates the camera and storage services with MAVLink mission execution:

  • When a mission starts (POST /start succeeds) a mission session begins:
      - a mission folder is created (missions/mission_<timestamp>/)
      - video recording starts automatically
  • During the mission a monitor thread watches MAVLink progress:
      - telemetry is sampled every TELEMETRY_LOG_INTERVAL_S into telemetry.json
      - every time MISSION_ITEM_REACHED reports a waypoint, the drone is held
        (LOITER) for ~WAYPOINT_HOLD_SECONDS, one photo is captured into
        images/, and the mission resumes (AUTO)
  • When the mission finishes (vehicle disarms, or connection is lost),
    recording stops automatically and telemetry.json / metadata.json are
    written.

Every camera/storage failure is contained: a failed photo or hold never
aborts the mission, and a streaming failure is invisible here by design.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from config import settings
from mavlink.commands import MAVLinkCommands
from mavlink.connection import connection, drone_state
from services.camera_service import camera_service
from services.recording_service import recording_service
from services.storage_service import MissionStorage, storage_service, utc_now_iso

logger = logging.getLogger(__name__)

_MONITOR_POLL_S = 0.2


class MissionRunner:
    """Owns the lifecycle of one active mission session at a time."""

    def __init__(self) -> None:
        self._cmds = MAVLinkCommands(connection)
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._storage: Optional[MissionStorage] = None
        self._mission_name: str = ""
        self._started_at: Optional[str] = None
        self._photos_captured = 0
        self._waypoints_reached = 0
        self._end_reason: str = ""

    # ── Public API ─────────────────────────────────────────────────────────────

    def on_mission_started(self, mission_name: str = "") -> None:
        """Begin a mission session. Called right after AUTO mode is confirmed."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                logger.warning("Mission session already active — ignoring new start.")
                return

            self._mission_name = mission_name
            # Clear any stale reached-seq from a previous mission so the new
            # mission's first MISSION_ITEM_REACHED is detected as an increase.
            drone_state.update(last_reached_waypoint=-1)
            self._storage = storage_service.create_mission_storage()
            self._started_at = utc_now_iso()
            self._photos_captured = 0
            self._waypoints_reached = 0
            self._end_reason = ""

            if not recording_service.start(self._storage.video_path):
                logger.warning("Recording did not start for mission session.")

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._monitor, name="mission-runner", daemon=True
            )
            self._thread.start()

        logger.info(
            "Mission session started: %s (folder=%s)",
            mission_name or "<unnamed>", self._storage.name,
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
                "waypoints_reached": self._waypoints_reached if active else 0,
                "photos_captured": self._photos_captured if active else 0,
                "recording": recording_service.is_recording,
            }

    # ── Monitor thread ─────────────────────────────────────────────────────────

    def _monitor(self) -> None:
        storage = self._storage
        last_reached = drone_state.last_reached_waypoint
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

                # ── Waypoint-reached events ────────────────────────────────────
                reached = drone_state.last_reached_waypoint
                if reached > last_reached:
                    last_reached = reached
                    self._waypoints_reached += 1
                    self._handle_waypoint_reached(reached, storage)

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

    def _handle_waypoint_reached(self, seq: int, storage: MissionStorage) -> None:
        """Hold ~2 s, capture one image, continue the mission.

        The hold uses LOITER/AUTO mode switching via the existing command
        layer. If the vehicle is not in AUTO (e.g. already in RTL at mission
        end) the hold is skipped and only the photo is taken. Any failure
        here is logged and swallowed — the mission always continues.
        """
        logger.info("Waypoint %d reached.", seq)
        held = False
        try:
            if drone_state.armed and drone_state.flight_mode.upper() == "AUTO":
                held = self._cmds.pause()
                if not held:
                    logger.warning("Hold at waypoint %d rejected — capturing photo anyway.", seq)
                time.sleep(settings.WAYPOINT_HOLD_SECONDS)
        except Exception:
            logger.exception("Hold at waypoint %d failed", seq)

        try:
            if camera_service.capture_photo(storage.next_image_path(seq)):
                self._photos_captured += 1
        except Exception:
            logger.exception("Photo capture at waypoint %d failed", seq)

        if held:
            try:
                if not self._cmds.resume():
                    logger.error(
                        "Failed to resume AUTO after hold at waypoint %d — "
                        "vehicle left in LOITER.", seq,
                    )
            except Exception:
                logger.exception("Resume after waypoint %d failed", seq)

    def _finalise(self, storage: MissionStorage) -> None:
        reason = self._end_reason or "unknown"
        logger.info("Mission session ending: %s", reason)

        try:
            recording_service.stop()
        except Exception:
            logger.exception("Failed to stop recording")

        try:
            storage.flush_telemetry()
        except Exception:
            logger.exception("Failed to write telemetry.json")

        try:
            storage.write_metadata(
                {
                    "mission_name": self._mission_name,
                    "folder": storage.name,
                    "started_at": self._started_at,
                    "ended_at": utc_now_iso(),
                    "end_reason": reason,
                    "waypoints_total": drone_state.waypoint_count,
                    "waypoints_reached": self._waypoints_reached,
                    "photos_captured": self._photos_captured,
                    "video_file": storage.video_path.name if storage.video_path.exists() else None,
                    "waypoint_hold_seconds": settings.WAYPOINT_HOLD_SECONDS,
                }
            )
        except Exception:
            logger.exception("Failed to write metadata.json")

        logger.info(
            "Mission session complete: %s (%d waypoints, %d photos)",
            storage.name, self._waypoints_reached, self._photos_captured,
        )


# Module-level singleton
mission_runner = MissionRunner()
