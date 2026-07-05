"""
Mission file management and upload coordination.

Responsibilities:
  • Receive and validate uploaded mission files (.waypoints or .plan)
  • Store them on disk with sanitised names
  • Delegate parsing to parser.loader (format-agnostic)
  • Upload the resulting Mission object to the Pixhawk via MAVLink
  • Keep the shared DroneState in sync with mission status
"""
import logging
import re
import uuid
from pathlib import Path
from typing import Optional

from config import settings
from mavlink.connection import connection, drone_state
from mavlink.mission_upload import MissionUploader
from models.mission import Mission
from parser.loader import load_mission
from parser.waypoint_parser import WaypointParseError
from services.mission_enrichment import enrich_mission

logger = logging.getLogger(__name__)


class MissionService:
    """Handles the full mission lifecycle from file upload to Pixhawk execution."""

    def __init__(self) -> None:
        self._uploader = MissionUploader(connection)
        self._current_mission: Optional[Mission] = None
        settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # ── Public API ─────────────────────────────────────────────────────────────

    def process_upload(self, filename: str, data: bytes) -> dict:
        """Parse, save, and (if connected) upload a mission file.

        Accepts .waypoints and .plan files — the loader selects the parser.

        Returns a dict with keys:
          mission_info        — parsed Mission
          uploaded_to_drone   — bool
          saved_path          — str
        """
        self._validate_file_meta(filename, len(data))
        safe_name = self._sanitise_filename(filename)

        # Delegate to the format-appropriate parser via the loader
        mission = load_mission(safe_name, data)

        # Densify sparse legs and insert native loiter/capture mission items
        # — a hand-authored or QGC-exported mission may have as few as 3-6
        # waypoints with no intermediate capture positions.
        mission = enrich_mission(mission)

        # Save to disk
        save_path = settings.UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{safe_name}"
        save_path.write_bytes(data)
        logger.info(
            "Mission file saved: %s (%d waypoints, format=%s).",
            save_path.name, mission.waypoint_count, mission.source_format,
        )

        self._current_mission = mission
        uploaded = False

        verified = False
        verification_message = ""

        if drone_state.connected:
            logger.info("Uploading mission to Pixhawk.")
            self._uploader.clear_mission()
            self._uploader.upload_mission(mission)
            drone_state.update(
                mission_uploaded=True,
                waypoint_count=mission.waypoint_count,
                current_waypoint=0,
            )
            uploaded = True
            logger.info(
                "Mission uploaded: %d items, %.2f km, ~%.0f min.",
                mission.waypoint_count,
                mission.total_distance_km,
                mission.estimated_duration_minutes,
            )

            # Read the mission back from the vehicle and verify every item
            verified, verification_message = self._uploader.verify_mission(mission)
            if not verified:
                logger.error("Mission verification failed: %s", verification_message)
            else:
                logger.info("Mission verification passed.")
        else:
            logger.info(
                "Drone not connected — mission parsed (%s) but not sent to vehicle.",
                mission.source_format,
            )

        return {
            "mission_info": mission,
            "uploaded_to_drone": uploaded,
            "saved_path": str(save_path),
            "verified": verified,
            "verification_message": verification_message,
        }

    def store_mission(self, mission: Mission) -> None:
        """Hold a Mission locally without uploading it to the vehicle."""
        self._current_mission = enrich_mission(mission)

    def load_generated(self, mission: Mission) -> dict:
        """Adopt an in-memory Mission (e.g. survey grid) and upload if connected.

        Mirrors process_upload() but skips file parsing/saving of raw bytes.
        """
        mission = enrich_mission(mission)
        self._current_mission = mission
        uploaded = False
        verified = False
        verification_message = ""

        if drone_state.connected:
            logger.info("Uploading generated mission to Pixhawk.")
            self._uploader.clear_mission()
            self._uploader.upload_mission(mission)
            drone_state.update(
                mission_uploaded=True,
                waypoint_count=mission.waypoint_count,
                current_waypoint=0,
            )
            uploaded = True
            verified, verification_message = self._uploader.verify_mission(mission)
            if not verified:
                logger.error("Mission verification failed: %s", verification_message)
            else:
                logger.info("Mission verification passed.")
        else:
            logger.info("Drone not connected — generated mission stored locally only.")

        return {
            "mission_info": mission,
            "uploaded_to_drone": uploaded,
            "verified": verified,
            "verification_message": verification_message,
        }

    def upload_current_to_drone(self) -> tuple[bool, str]:
        """Push the already-parsed mission to the Pixhawk (used after late connect).

        Returns (verified, verification_message).
        """
        if not self._current_mission:
            raise RuntimeError("No mission loaded. Upload a .waypoints or .plan file first.")
        if not drone_state.connected:
            raise RuntimeError("Not connected to Pixhawk.")
        self._uploader.clear_mission()
        self._uploader.upload_mission(self._current_mission)
        drone_state.update(
            mission_uploaded=True,
            waypoint_count=self._current_mission.waypoint_count,
            current_waypoint=0,
        )
        logger.info(
            "Pending mission uploaded to drone (%d items, format=%s).",
            self._current_mission.waypoint_count,
            self._current_mission.source_format,
        )
        verified, verification_message = self._uploader.verify_mission(self._current_mission)
        if not verified:
            logger.error("Mission verification failed: %s", verification_message)
        return verified, verification_message

    def clear_mission(self) -> None:
        """Clear mission from vehicle and reset local state."""
        if drone_state.connected:
            self._uploader.clear_mission()
        drone_state.update(mission_uploaded=False, waypoint_count=0, current_waypoint=0)
        self._current_mission = None
        logger.info("Mission cleared.")

    @property
    def current_mission(self) -> Optional[Mission]:
        return self._current_mission

    # ── Internal ───────────────────────────────────────────────────────────────

    def _validate_file_meta(self, filename: str, size: int) -> None:
        ext = Path(filename).suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise WaypointParseError(
                f"File type '{ext}' not accepted. "
                f"Supported formats: {', '.join(sorted(settings.ALLOWED_EXTENSIONS))}."
            )
        if size > settings.MAX_UPLOAD_BYTES:
            raise WaypointParseError(
                f"File size {size // 1024} KB exceeds the "
                f"{settings.MAX_UPLOAD_BYTES // 1024 // 1024} MB limit."
            )
        if size == 0:
            raise WaypointParseError("Uploaded file is empty.")

    @staticmethod
    def _sanitise_filename(filename: str) -> str:
        """Strip path components, remove dangerous characters, preserve extension."""
        name = Path(filename).name
        stem = Path(name).stem
        ext  = Path(name).suffix.lower()
        safe_stem = re.sub(r"[^\w\-]", "_", stem)[:120]
        return f"{safe_stem}{ext}"


mission_service = MissionService()
