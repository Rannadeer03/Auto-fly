"""Mission storage service.

Owns the on-disk layout of recorded missions:

    missions/
        mission_<YYYYMMDD_HHMMSS>/
            video.mp4
            images/
                waypoint_001.jpg
                ...
            telemetry.json
            metadata.json
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


class MissionStorage:
    """Handle to a single mission's folder."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.images_dir = root / "images"
        self.video_path = root / "video.mp4"
        self.telemetry_path = root / "telemetry.json"
        self.metadata_path = root / "metadata.json"

        self._telemetry_lock = threading.Lock()
        self._telemetry_samples: list[dict] = []

        self.root.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return self.root.name

    def next_image_path(self, waypoint_seq: int) -> Path:
        return self.images_dir / f"waypoint_{waypoint_seq:03d}.jpg"

    def append_telemetry(self, sample: dict) -> None:
        with self._telemetry_lock:
            self._telemetry_samples.append(sample)

    def flush_telemetry(self) -> None:
        with self._telemetry_lock:
            samples = list(self._telemetry_samples)
        self.telemetry_path.write_text(json.dumps(samples, indent=2))

    def write_metadata(self, metadata: dict) -> None:
        self.metadata_path.write_text(json.dumps(metadata, indent=2, default=str))
        logger.info("Mission metadata written: %s", self.metadata_path)


class StorageService:
    """Creates and lists mission folders under settings.MISSIONS_DIR."""

    def __init__(self) -> None:
        settings.MISSIONS_DIR.mkdir(parents=True, exist_ok=True)

    def create_mission_storage(self) -> MissionStorage:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        root = settings.MISSIONS_DIR / f"mission_{timestamp}"
        # Guard against two missions starting within the same second
        suffix = 1
        while root.exists():
            root = settings.MISSIONS_DIR / f"mission_{timestamp}_{suffix}"
            suffix += 1
        storage = MissionStorage(root)
        logger.info("Mission storage created: %s", root)
        return storage

    def list_missions(self) -> list[dict]:
        """Return summaries of every stored mission, newest first."""
        results: list[dict] = []
        if not settings.MISSIONS_DIR.exists():
            return results
        for entry in sorted(settings.MISSIONS_DIR.iterdir(), reverse=True):
            if not entry.is_dir() or not entry.name.startswith("mission_"):
                continue
            metadata: Optional[dict] = None
            meta_file = entry / "metadata.json"
            if meta_file.exists():
                try:
                    metadata = json.loads(meta_file.read_text())
                except (json.JSONDecodeError, OSError):
                    metadata = None
            images_dir = entry / "images"
            results.append(
                {
                    "name": entry.name,
                    "path": str(entry),
                    "has_video": (entry / "video.mp4").exists(),
                    "image_count": (
                        len(list(images_dir.glob("*.jpg"))) if images_dir.exists() else 0
                    ),
                    "metadata": metadata,
                }
            )
        return results


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Module-level singleton
storage_service = StorageService()
