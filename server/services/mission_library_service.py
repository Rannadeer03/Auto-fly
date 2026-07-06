"""
Mission Library storage service.

Holds reusable, pre-flight mission *plans* — name, description, the drawn
polygon, flight parameters, and the generated waypoints/statistics — so a
survey can be saved once and re-used (viewed, searched, renamed, duplicated,
downloaded, or uploaded to the drone again) without redrawing it.

This is deliberately separate from services/storage_service.py, which
archives *post-flight* sessions (photos, video, logs) under MISSIONS_DIR.
A library entry is a plan; a storage_service mission is a flight record.

Layout (one JSON file per plan, mirroring storage_service.py's
sanitized-name + timestamp convention):

    mission_library/
        <Sanitized_Name>_<YYYYMMDD_HHMMSS>.json
"""
from __future__ import annotations

import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from config import settings
from models.mission import Mission

logger = logging.getLogger(__name__)

# Same convention as storage_service._MISSION_NAME_RE — validated before any
# filesystem access, so path traversal through the API is impossible.
_LIBRARY_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+_\d{8}_\d{6}(_\d+)?$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitise_name(name: str) -> str:
    stripped = re.sub(r"[^\w\-]", "_", name.strip())
    return stripped[:80].strip("_")


class MissionLibraryService:
    """Creates, lists, and mutates saved mission plans under MISSION_LIBRARY_DIR."""

    def __init__(self) -> None:
        settings.MISSION_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    # ── Path helpers ───────────────────────────────────────────────────────────

    def _path_for(self, entry_id: str) -> Optional[Path]:
        if not _LIBRARY_ID_RE.match(entry_id):
            return None
        return settings.MISSION_LIBRARY_DIR / f"{entry_id}.json"

    def _new_id(self, name: str) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = _sanitise_name(name) or "mission"
        base = f"{safe_name}_{timestamp}"
        entry_id = base
        suffix = 1
        while (settings.MISSION_LIBRARY_DIR / f"{entry_id}.json").exists():
            entry_id = f"{base}_{suffix}"
            suffix += 1
        return entry_id

    # ── CRUD ───────────────────────────────────────────────────────────────────

    def save(
        self,
        name: str,
        description: str,
        mission: Mission,
        plan_info: Optional[dict],
        *,
        mode: str = "survey",
        polygon: Optional[list[tuple[float, float]]] = None,
        params: Optional[dict] = None,
        home: Optional[tuple[float, float]] = None,
        manual_items: Optional[list[dict]] = None,
    ) -> dict:
        """Persist a new library entry.

        *mode* is a free-form discriminator ("survey" | "manual") — absent
        on any entry saved before this field existed, which callers should
        treat as "survey" (see _summarise). Survey entries carry
        polygon/params (regenerable via grid_planner); manual entries carry
        home/manual_items — the same ordered, tagged mission-item list
        server/models/manual_mission.py validates on the request side
        (regenerable via manual_mission_builder; "launch" is just
        manual_items[0], a takeoff-type item — no separate field for it).
        Both shapes are optional here so this one method serves either
        without forcing irrelevant fields on the other.
        """
        with self._lock:
            entry_id = self._new_id(name)
            record: dict = {
                "id": entry_id,
                "name": name.strip() or entry_id,
                "description": description.strip(),
                "created_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
                "mode": mode,
                "mission": mission.model_dump(),
                "plan_info": plan_info,
            }
            if polygon is not None:
                record["polygon"] = [list(p) for p in polygon]
            if params is not None:
                record["params"] = params
            if home is not None:
                record["home"] = list(home)
            if manual_items is not None:
                record["manual_items"] = manual_items
            path = settings.MISSION_LIBRARY_DIR / f"{entry_id}.json"
            path.write_text(json.dumps(record, indent=2, default=str))
            logger.info("Mission library entry saved: %s (mode=%s)", entry_id, mode)
            return record

    def get(self, entry_id: str) -> Optional[dict]:
        """Raw stored record — full mission/polygon/params, no derived fields."""
        path = self._path_for(entry_id)
        if path is None or not path.exists():
            return None
        return self._read_json(path)

    def get_detail(self, entry_id: str) -> Optional[dict]:
        """Full detail for the API/frontend: the raw record plus the same
        flattened stats fields (waypoint_count, total_distance_km, ...) the
        list summary exposes, so LibraryEntry is always a superset of
        LibrarySummary regardless of which endpoint populated it."""
        record = self.get(entry_id)
        if record is None:
            return None
        return {**record, **self._summarise(record)}

    def list(self, query: str = "") -> list[dict]:
        results: list[dict] = []
        if not settings.MISSION_LIBRARY_DIR.exists():
            return results
        q = query.strip().lower()
        for path in sorted(settings.MISSION_LIBRARY_DIR.glob("*.json"), reverse=True):
            if not _LIBRARY_ID_RE.match(path.stem):
                continue
            record = self._read_json(path)
            if record is None:
                continue
            summary = self._summarise(record)
            if q and q not in self._searchable_text(record):
                continue
            results.append(summary)
        return results

    def update(self, entry_id: str, name: Optional[str], description: Optional[str]) -> Optional[dict]:
        path = self._path_for(entry_id)
        if path is None or not path.exists():
            return None
        with self._lock:
            record = self._read_json(path)
            if record is None:
                return None
            if name is not None and name.strip():
                record["name"] = name.strip()
            if description is not None:
                record["description"] = description.strip()
            record["updated_at"] = _utc_now_iso()
            path.write_text(json.dumps(record, indent=2, default=str))
            logger.info("Mission library entry updated: %s", entry_id)
            return {**record, **self._summarise(record)}

    def duplicate(self, entry_id: str, new_name: Optional[str] = None) -> Optional[dict]:
        source_path = self._path_for(entry_id)
        if source_path is None or not source_path.exists():
            return None
        with self._lock:
            record = self._read_json(source_path)
            if record is None:
                return None
            name = (new_name or f"{record['name']} (Copy)").strip()
            new_id = self._new_id(name)
            record = {
                **record,
                "id": new_id,
                "name": name,
                "created_at": _utc_now_iso(),
                "updated_at": _utc_now_iso(),
            }
            path = settings.MISSION_LIBRARY_DIR / f"{new_id}.json"
            path.write_text(json.dumps(record, indent=2, default=str))
            logger.info("Mission library entry '%s' duplicated to '%s'.", entry_id, new_id)
            return {**record, **self._summarise(record)}

    def delete(self, entry_id: str) -> bool:
        path = self._path_for(entry_id)
        if path is None or not path.exists():
            return False
        path.unlink()
        logger.info("Mission library entry deleted: %s", entry_id)
        return True

    # ── Internal ───────────────────────────────────────────────────────────────

    @staticmethod
    def _summarise(record: dict) -> dict:
        mission = record.get("mission") or {}
        return {
            "id": record["id"],
            "name": record.get("name"),
            "description": record.get("description", ""),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            # Entries saved before "mode" existed have no such key — treat
            # those (survey-only, at the time) as "survey".
            "mode": record.get("mode", "survey"),
            "waypoint_count": mission.get("waypoint_count", 0),
            "total_distance_km": mission.get("total_distance_km", 0.0),
            "estimated_duration_minutes": mission.get("estimated_duration_minutes", 0.0),
            "estimated_battery_percent": mission.get("estimated_battery_percent", 0.0),
            "params": record.get("params", {}),
        }

    @staticmethod
    def _searchable_text(record: dict) -> str:
        return " ".join(
            str(v) for v in (record.get("name"), record.get("description"), record.get("id")) if v
        ).lower()

    @staticmethod
    def _read_json(path: Path) -> Optional[dict]:
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to read mission library entry: %s", path)
            return None


mission_library_service = MissionLibraryService()
