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
            index.json            # auto-generated file index + flight stats
            mapping/
                photos.json       # per-photo geotags for map stitching
"""

from __future__ import annotations

import io
import json
import logging
import re
import shutil
import threading
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from config import settings

# Folder names created by create_mission_storage(): mission_<ts> or mission_<ts>_<n>
_MISSION_NAME_RE = re.compile(r"^mission_\d{8}_\d{6}(_\d+)?$")

_ZIP_CHUNK_BYTES = 512 * 1024

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

    def resolve_mission_root(self, name: str) -> Optional[Path]:
        """Return the mission folder for *name*, or None.

        Validates the name against the folder-name pattern before touching the
        filesystem, so path traversal through the API is impossible.
        """
        if not _MISSION_NAME_RE.match(name):
            return None
        root = settings.MISSIONS_DIR / name
        return root if root.is_dir() else None

    def list_missions(self, query: str = "") -> list[dict]:
        """Return summaries of every stored mission, newest first.

        *query* filters (case-insensitive substring) on the folder name and
        key metadata fields (mission name, dates, end reason).
        """
        results: list[dict] = []
        if not settings.MISSIONS_DIR.exists():
            return results
        q = query.strip().lower()
        for entry in sorted(settings.MISSIONS_DIR.iterdir(), reverse=True):
            if not entry.is_dir() or not _MISSION_NAME_RE.match(entry.name):
                continue
            summary = self.mission_summary(entry)
            if q and not self._matches_query(summary, q):
                continue
            results.append(summary)
        return results

    @staticmethod
    def _matches_query(summary: dict, q: str) -> bool:
        meta = summary.get("metadata") or {}
        haystack = " ".join(
            str(v)
            for v in (
                summary["name"],
                meta.get("mission_name"),
                meta.get("started_at"),
                meta.get("ended_at"),
                meta.get("end_reason"),
            )
            if v
        ).lower()
        return q in haystack

    def mission_summary(self, entry: Path) -> dict:
        metadata = self._read_json(entry / "metadata.json")
        index = self.ensure_index(entry)
        photos_dir = entry / "photos"
        return {
            "name": entry.name,
            "has_video": (entry / "video.mp4").exists(),
            "photo_count": (
                len(list(photos_dir.glob("*.jpg"))) if photos_dir.exists() else 0
            ),
            "has_mapping_index": (entry / "mapping" / "photos.json").exists(),
            "has_log": (entry / "logs" / "mission.log").exists(),
            "metadata": metadata,
            "total_size_bytes": index.get("total_size_bytes", 0) if index else 0,
            "stats": index.get("stats") if index else None,
        }

    def get_mission_detail(self, name: str) -> Optional[dict]:
        """Full detail for one stored mission: metadata, indices, plan, stats."""
        root = self.resolve_mission_root(name)
        if root is None:
            return None
        detail = self.mission_summary(root)
        detail["photos"] = self._read_json(root / "mapping" / "photos.json")
        detail["mission"] = self._read_json(root / "mission.json")
        index = self.ensure_index(root)
        detail["files"] = index.get("files", []) if index else []
        return detail

    # ── Mission index (auto-generated after every mission) ─────────────────────

    def build_index(self, root: Path) -> dict:
        """Scan a mission folder and write index.json: every file with its
        size, plus flight statistics derived from telemetry.json."""
        files: list[dict] = []
        total = 0
        for f in sorted(root.rglob("*")):
            if not f.is_file() or f.name == "index.json":
                continue
            size = f.stat().st_size
            files.append({"path": str(f.relative_to(root)), "size": size})
            total += size
        index = {
            "name": root.name,
            "generated_at": utc_now_iso(),
            "file_count": len(files),
            "total_size_bytes": total,
            "stats": self._telemetry_stats(root / "telemetry.json"),
            "files": files,
        }
        (root / "index.json").write_text(json.dumps(index, indent=2))
        logger.info("Mission index written: %s (%d files)", root.name, len(files))
        return index

    def ensure_index(self, root: Path) -> Optional[dict]:
        """Load index.json, building it first for pre-existing missions that
        were recorded before indexing existed. Never indexes a folder that is
        still missing metadata.json (i.e. a mission still in progress)."""
        index = self._read_json(root / "index.json")
        if index is not None:
            return index
        if not (root / "metadata.json").exists():
            return None  # mission still recording — index is built at finalise
        try:
            return self.build_index(root)
        except OSError:
            logger.exception("Failed to build index for %s", root.name)
            return None

    @staticmethod
    def _telemetry_stats(telemetry_path: Path) -> Optional[dict]:
        """Derive flight statistics from the recorded telemetry samples."""
        samples = StorageService._read_json(telemetry_path)
        if not samples or not isinstance(samples, list):
            return None
        from parser.waypoint_parser import haversine_m

        distance = 0.0
        max_alt = 0.0
        max_speed = 0.0
        prev: Optional[tuple[float, float]] = None
        voltages = []
        for s in samples:
            lat, lon = s.get("latitude", 0.0), s.get("longitude", 0.0)
            if lat or lon:
                if prev is not None:
                    distance += haversine_m(prev[0], prev[1], lat, lon)
                prev = (lat, lon)
            max_alt = max(max_alt, s.get("altitude_rel", 0.0) or 0.0)
            max_speed = max(max_speed, s.get("ground_speed", 0.0) or 0.0)
            v = s.get("battery_voltage", 0.0) or 0.0
            if v > 0:
                voltages.append(v)
        return {
            "samples": len(samples),
            "distance_m": round(distance, 1),
            "max_altitude_rel_m": round(max_alt, 1),
            "max_ground_speed_ms": round(max_speed, 2),
            "battery_voltage_start": voltages[0] if voltages else None,
            "battery_voltage_end": voltages[-1] if voltages else None,
        }

    # ── Deletion ───────────────────────────────────────────────────────────────

    def delete_mission(self, name: str) -> bool:
        root = self.resolve_mission_root(name)
        if root is None:
            return False
        shutil.rmtree(root)
        logger.info("Mission deleted: %s", name)
        return True

    # ── ZIP export (streamed — nothing is duplicated on disk) ─────────────────

    def zip_stream(self, root: Path) -> Iterator[bytes]:
        """Yield a ZIP archive of the whole mission folder, chunk by chunk.

        Files are read straight from the mission folder and streamed out
        through an in-memory buffer — no temporary copy is ever written.
        ZIP_STORED is used because photos/video are already compressed.
        """
        buffer = _StreamBuffer()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            for f in sorted(root.rglob("*")):
                if not f.is_file():
                    continue
                arcname = f"{root.name}/{f.relative_to(root)}"
                info = zipfile.ZipInfo.from_file(f, arcname)
                with f.open("rb") as src, zf.open(info, "w") as dst:
                    while chunk := src.read(_ZIP_CHUNK_BYTES):
                        dst.write(chunk)
                        if (data := buffer.take()):
                            yield data
                if (data := buffer.take()):
                    yield data
        if (data := buffer.take()):
            yield data

    @staticmethod
    def _read_json(path: Path):
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None


class _StreamBuffer(io.RawIOBase):
    """Write-only file object that hands written bytes back via take().

    zipfile detects the stream is unseekable and emits data descriptors,
    which every mainstream unzip tool supports.
    """

    def __init__(self) -> None:
        self._chunks: list[bytes] = []

    def writable(self) -> bool:
        return True

    def write(self, b) -> int:
        self._chunks.append(bytes(b))
        return len(b)

    def take(self) -> bytes:
        data = b"".join(self._chunks)
        self._chunks.clear()
        return data


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Module-level singleton
storage_service = StorageService()
