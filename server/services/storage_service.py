"""Mission storage service.

Owns the on-disk layout of recorded missions. Every mission is completely
isolated in its own folder:

    missions/
        mission_<YYYYMMDD_HHMMSS>/
            video.mp4
            photos/
                photo_00001.jpg
                ...
            logs/
                mission.log
            telemetry.json
            metadata.json
            mission.json          # the flight plan that was executed
            mapping/
                photos.json       # per-photo geotags for map stitching
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
        self.photos_dir = root / "photos"
        self.logs_dir = root / "logs"
        self.mapping_dir = root / "mapping"
        self.video_path = root / "video.mp4"
        self.telemetry_path = root / "telemetry.json"
        self.metadata_path = root / "metadata.json"
        self.mission_path = root / "mission.json"
        self.photo_index_path = self.mapping_dir / "photos.json"
        self.log_path = self.logs_dir / "mission.log"

        self._lock = threading.Lock()
        self._telemetry_samples: list[dict] = []
        self._photo_records: list[dict] = []

        for d in (self.root, self.photos_dir, self.logs_dir, self.mapping_dir):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return self.root.name

    def next_photo_path(self, photo_number: int) -> Path:
        return self.photos_dir / f"photo_{photo_number:05d}.jpg"

    def record_photo(self, path: Path, telemetry: dict) -> None:
        """Store a geotag record for a captured photo (used for mapping)."""
        with self._lock:
            self._photo_records.append(
                {
                    "file": f"photos/{path.name}",
                    "timestamp": utc_now_iso(),
                    "latitude": telemetry.get("latitude", 0.0),
                    "longitude": telemetry.get("longitude", 0.0),
                    "altitude_rel": telemetry.get("altitude_rel", 0.0),
                    "altitude_msl": telemetry.get("altitude_msl", 0.0),
                    "heading": telemetry.get("heading", 0),
                    "ground_speed": telemetry.get("ground_speed", 0.0),
                }
            )

    def append_telemetry(self, sample: dict) -> None:
        with self._lock:
            self._telemetry_samples.append(sample)

    def write_mission(self, mission_dict: Optional[dict]) -> None:
        """Persist the executed flight plan as mission.json."""
        self.mission_path.write_text(
            json.dumps(mission_dict or {}, indent=2, default=str)
        )

    def flush(self) -> None:
        """Write telemetry.json and mapping/photos.json to disk."""
        with self._lock:
            samples = list(self._telemetry_samples)
            photos = list(self._photo_records)
        self.telemetry_path.write_text(json.dumps(samples, indent=2))
        self.photo_index_path.write_text(json.dumps(photos, indent=2))

    def write_metadata(self, metadata: dict) -> None:
        self.metadata_path.write_text(json.dumps(metadata, indent=2, default=str))
        logger.info("Mission metadata written: %s", self.metadata_path)

    @property
    def photo_count(self) -> int:
        with self._lock:
            return len(self._photo_records)


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
            results.append(self.mission_summary(entry))
        return results

    def mission_summary(self, entry: Path) -> dict:
        metadata: Optional[dict] = None
        meta_file = entry / "metadata.json"
        if meta_file.exists():
            try:
                metadata = json.loads(meta_file.read_text())
            except (json.JSONDecodeError, OSError):
                metadata = None
        photos_dir = entry / "photos"
        return {
            "name": entry.name,
            "path": str(entry),
            "has_video": (entry / "video.mp4").exists(),
            "photo_count": (
                len(list(photos_dir.glob("*.jpg"))) if photos_dir.exists() else 0
            ),
            "has_mapping_index": (entry / "mapping" / "photos.json").exists(),
            "metadata": metadata,
        }

    def get_mission_detail(self, name: str) -> Optional[dict]:
        """Full detail for one stored mission: metadata, photo index, plan."""
        root = settings.MISSIONS_DIR / name
        if not root.is_dir() or not name.startswith("mission_"):
            return None
        detail = self.mission_summary(root)
        for key, rel in (
            ("photos", Path("mapping/photos.json")),
            ("mission", Path("mission.json")),
        ):
            f = root / rel
            if f.exists():
                try:
                    detail[key] = json.loads(f.read_text())
                except (json.JSONDecodeError, OSError):
                    detail[key] = None
        return detail


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Module-level singleton
storage_service = StorageService()
