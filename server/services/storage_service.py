"""Mission storage service.

Owns the on-disk layout of recorded missions. Every mission is completely
isolated in its own folder, named `<sanitized_mission_name>_<timestamp>`
(or `mission_<timestamp>` when no name was given):

    missions/
        <Mission_Name>_<YYYYMMDD_HHMMSS>/
            video.mp4              # flight recording
            images/
                photo_00001.jpg
                thumbs/
                    photo_00001_thumb.jpg
                ...
            logs/
                mission.log
            telemetry.json         # continuous telemetry samples for the whole flight
            statistics.json        # mission-level flight statistics (see MissionSessionContext)
            metadata.json          # mission summary + full per-image metadata
            metadata.csv           # per-image metadata, flattened
            mission.json           # the flight plan that was executed
            index.json             # auto-generated file index + flight stats
            frame_sync.json        # the same continuous telemetry samples as telemetry.json

Every field above is exposed through services/mission_session.py's
MissionSessionContext so other services never need to build their own
mission folder or filename.
"""

from __future__ import annotations

import csv
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

# Folder names created by create_mission_storage(): safe characters only,
# always ending in _<8 digit date>_<6 digit time> (optionally _<n> for
# same-second collisions) — this is what resolve_mission_root() validates
# against, so path traversal through the API is impossible.
_MISSION_NAME_RE = re.compile(r"^[A-Za-z0-9_\-]+_\d{8}_\d{6}(_\d+)?$")

_ZIP_CHUNK_BYTES = 512 * 1024

# Per-image metadata.csv column order — kept explicit (rather than "whatever
# dict.keys() happens to be") so the CSV header never reorders between runs.
IMAGE_METADATA_FIELDS = [
    "filename",
    "mission_name",
    "mission_id",
    "timestamp",
    "latitude",
    "longitude",
    "altitude_rel",
    "altitude_msl",
    "heading_deg",
    "pitch_deg",
    "roll_deg",
    "camera_orientation_deg",
    "waypoint_number",
    "capture_sequence",
    "drone_speed_ms",
    "gps_fix_quality",
    "satellites_visible",
]

logger = logging.getLogger(__name__)


class MissionStorage:
    """Handle to a single mission's folder."""

    def __init__(self, root: Path, mission_id: str, mission_name: str) -> None:
        self.root = root
        self.mission_id = mission_id
        self.mission_name = mission_name

        self.images_dir = root / "images"
        self.thumbs_dir = self.images_dir / "thumbs"
        self.logs_dir = root / "logs"
        self.video_path = root / "video.mp4"
        self.telemetry_path = root / "telemetry.json"
        self.metadata_json_path = root / "metadata.json"
        self.metadata_csv_path = root / "metadata.csv"
        self.mission_path = root / "mission.json"
        self.log_path = self.logs_dir / "mission.log"
        self.statistics_path = root / "statistics.json"
        self.frame_sync_path = root / "frame_sync.json"

        self._lock = threading.Lock()
        self._telemetry_samples: list[dict] = []
        self._image_records: list[dict] = []

        for d in (self.root, self.images_dir, self.thumbs_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return self.root.name

    def next_photo_path(self, photo_number: int) -> Path:
        return self.images_dir / f"photo_{photo_number:05d}.jpg"

    def thumb_path_for(self, photo_path: Path) -> Path:
        return self.thumbs_dir / f"{photo_path.stem}_thumb.jpg"

    def record_photo(
        self,
        path: Path,
        telemetry: dict,
        *,
        waypoint_number: int,
        capture_sequence: int,
        camera_orientation_deg: float,
    ) -> None:
        """Store full metadata for one captured photo (used for mapping,
        the frontend gallery, and metadata.json/metadata.csv)."""
        from mavlink.connection import GPS_FIX_NAMES  # local import avoids a cycle

        with self._lock:
            self._image_records.append(
                {
                    "filename": f"images/{path.name}",
                    "mission_name": self.mission_name,
                    "mission_id": self.mission_id,
                    "timestamp": utc_now_iso(),
                    "latitude": telemetry.get("latitude", 0.0),
                    "longitude": telemetry.get("longitude", 0.0),
                    "altitude_rel": telemetry.get("altitude_rel", 0.0),
                    "altitude_msl": telemetry.get("altitude_msl", 0.0),
                    "heading_deg": telemetry.get("yaw", 0.0),
                    "pitch_deg": telemetry.get("pitch", 0.0),
                    "roll_deg": telemetry.get("roll", 0.0),
                    "camera_orientation_deg": camera_orientation_deg,
                    "waypoint_number": waypoint_number,
                    "capture_sequence": capture_sequence,
                    "drone_speed_ms": telemetry.get("ground_speed", 0.0),
                    "gps_fix_quality": GPS_FIX_NAMES.get(
                        telemetry.get("gps_fix_type", 0), "Unknown"
                    ),
                    "satellites_visible": telemetry.get("gps_satellites", 0),
                }
            )

    def append_telemetry(self, sample: dict) -> None:
        with self._lock:
            self._telemetry_samples.append(sample)

    @property
    def telemetry_samples(self) -> list[dict]:
        """Copy of every telemetry sample collected so far this mission —
        the same continuous samples flush() writes to telemetry.json."""
        with self._lock:
            return list(self._telemetry_samples)

    def write_mission(self, mission_dict: Optional[dict]) -> None:
        """Persist the executed flight plan as mission.json."""
        self.mission_path.write_text(
            json.dumps(mission_dict or {}, indent=2, default=str)
        )

    def flush(self) -> None:
        """Write telemetry.json to disk."""
        with self._lock:
            samples = list(self._telemetry_samples)
        self.telemetry_path.write_text(json.dumps(samples, indent=2))

    def write_metadata(self, summary: dict) -> None:
        """Write metadata.json (summary + full per-image array) and
        metadata.csv (per-image rows only) — called once, at mission end."""
        with self._lock:
            images = list(self._image_records)

        payload = {**summary, "mission_id": self.mission_id, "images": images}
        self.metadata_json_path.write_text(json.dumps(payload, indent=2, default=str))

        with self.metadata_csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=IMAGE_METADATA_FIELDS)
            writer.writeheader()
            writer.writerows(images)

        logger.info(
            "Mission metadata written: %s (%d images).", self.metadata_json_path, len(images)
        )

    @property
    def image_count(self) -> int:
        with self._lock:
            return len(self._image_records)

    def write_statistics(self, stats: dict) -> None:
        """Write statistics.json — kept separate from metadata.json so a
        future phase can extend mission statistics without touching the
        flight-record file."""
        self.statistics_path.write_text(json.dumps(stats, indent=2, default=str))

    def write_frame_sync(self, records: list[dict]) -> None:
        """Write frame_sync.json — the same continuous telemetry samples as
        telemetry.json, kept as a separate named artifact. One telemetry
        source (drone_state, sampled by the mission monitor loop); no
        separate reader or cached snapshot."""
        self.frame_sync_path.write_text(json.dumps(records, indent=2, default=str))


class StorageService:
    """Creates and lists mission folders under settings.MISSIONS_DIR."""

    def __init__(self) -> None:
        settings.MISSIONS_DIR.mkdir(parents=True, exist_ok=True)

    def create_mission_storage(self, mission_name: str = "") -> MissionStorage:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self._sanitise_name(mission_name)
        base = f"{safe_name}_{timestamp}" if safe_name else f"mission_{timestamp}"

        mission_id = base
        root = settings.MISSIONS_DIR / mission_id
        # Guard against two missions starting within the same second
        suffix = 1
        while root.exists():
            mission_id = f"{base}_{suffix}"
            root = settings.MISSIONS_DIR / mission_id
            suffix += 1

        storage = MissionStorage(root, mission_id=mission_id, mission_name=mission_name or mission_id)
        logger.info("Mission storage created: %s", root)
        return storage

    @staticmethod
    def _sanitise_name(name: str) -> str:
        stripped = re.sub(r"[^\w\-]", "_", name.strip())
        return stripped[:80].strip("_")

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
        images = metadata.pop("images", []) if metadata else []
        index = self.ensure_index(entry)
        return {
            "name": entry.name,
            "mission_id": (metadata or {}).get("mission_id", entry.name),
            "has_video": (entry / "video.mp4").exists(),
            "photo_count": len(images),
            "has_log": (entry / "logs" / "mission.log").exists(),
            "metadata": metadata,
            "total_size_bytes": index.get("total_size_bytes", 0) if index else 0,
            "stats": index.get("stats") if index else None,
        }

    def get_mission_detail(self, name: str) -> Optional[dict]:
        """Full detail for one stored mission: metadata, per-image metadata,
        executed plan, file index, and telemetry-derived flight statistics."""
        root = self.resolve_mission_root(name)
        if root is None:
            return None
        metadata = self._read_json(root / "metadata.json")
        images = metadata.pop("images", []) if metadata else []
        index = self.ensure_index(root)
        return {
            "name": root.name,
            "mission_id": (metadata or {}).get("mission_id", root.name),
            "has_video": (root / "video.mp4").exists(),
            "photo_count": len(images),
            "has_log": (root / "logs" / "mission.log").exists(),
            "metadata": metadata,
            "total_size_bytes": index.get("total_size_bytes", 0) if index else 0,
            "stats": index.get("stats") if index else None,
            "images": images,
            "mission": self._read_json(root / "mission.json"),
            "files": index.get("files", []) if index else [],
        }

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
            logger.warning("Could not read/parse %s — treating as missing.", path, exc_info=True)
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
