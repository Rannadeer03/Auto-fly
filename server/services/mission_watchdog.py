"""GCS-independent mission-session watchdog.

Passively watches MAVLink telemetry for the vehicle entering AUTO mode
while armed and, when no mission session is already running, starts one —
regardless of *how* AUTO was triggered (the website's own POST /start, an
RC transmitter mode switch, or QGroundControl connected directly). This is
what makes recording + hover-capture automation work identically no matter
which app the pilot used to fly the mission.
"""
from __future__ import annotations

import logging
import threading

from mavlink.connection import connection, drone_state
from mavlink.mission_upload import MissionUploader, MissionUploadError

logger = logging.getLogger(__name__)

_POLL_S = 0.5


def _watchdog_loop(stop_event: threading.Event) -> None:
    from services.mission_runner import mission_runner
    from services.mission_service import mission_service

    uploader = MissionUploader(connection)

    while not stop_event.is_set():
        stop_event.wait(_POLL_S)
        if stop_event.is_set():
            break

        if not (drone_state.armed and drone_state.flight_mode.upper() == "AUTO"):
            continue
        if mission_runner.is_active:
            continue

        mission = mission_service.current_mission
        mission_name = mission.filename if mission else ""
        mission_dict = mission.model_dump() if mission else None

        if mission is None:
            # AUTO was triggered without this backend ever uploading a
            # mission this session (e.g. QGroundControl connected and
            # uploaded directly) — read the mission back off the vehicle so
            # capture automation still has planned waypoint data.
            try:
                downloaded = uploader.download_mission()
                mission_name = downloaded.filename
                mission_dict = downloaded.model_dump()
                logger.info(
                    "Watchdog: downloaded %d-item mission from the vehicle "
                    "(not uploaded via this backend).",
                    downloaded.waypoint_count,
                )
            except MissionUploadError as exc:
                logger.warning(
                    "Watchdog: AUTO detected but could not read the mission "
                    "from the vehicle (%s) — starting the session without "
                    "capture waypoint data; recording still runs.", exc,
                )

        logger.info(
            "Watchdog: AUTO + armed detected — starting mission session "
            "(mission=%s).", mission_name or "<unknown>",
        )
        try:
            mission_runner.on_mission_started(mission_name, mission_dict)
        except Exception:
            logger.exception("Watchdog: failed to start mission session")


def start(stop_event: threading.Event) -> threading.Thread:
    """Start the watchdog as a daemon thread. Idempotent per-call — the
    caller (main.py lifespan) only calls this once at process startup."""
    thread = threading.Thread(
        target=_watchdog_loop, args=(stop_event,), name="mission-watchdog", daemon=True,
    )
    thread.start()
    logger.info("Mission watchdog started (GCS-independent AUTO detection).")
    return thread
