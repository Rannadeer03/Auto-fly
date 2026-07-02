"""Central logging configuration for the DronAI backend.

Why a dedicated module: this service runs unattended on a flying drone, so a
live terminal is often unavailable. Every important lifecycle event (camera
open/close, peer connect/disconnect, ICE transitions, fps, errors) needs to
survive to disk for post-flight debugging, not just scroll past in a console
that nobody is watching.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging(log_dir: Path, level: int = logging.INFO) -> None:
    """Configure the root logger once at process startup.

    Adds a console handler (for live debugging) and a size-capped rotating
    file handler (for post-flight log retrieval). Safe to call more than
    once; subsequent calls are no-ops so importing modules can call it
    defensively without duplicating handlers.
    """
    global _configured
    if _configured:
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.handlers.RotatingFileHandler(
        log_dir / "dronai.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # aiortc and aioice are extremely verbose at DEBUG/INFO; keep them at
    # WARNING so our own log lines aren't drowned out, but still surface
    # genuine problems from those libraries.
    logging.getLogger("aiortc").setLevel(logging.WARNING)
    logging.getLogger("aioice").setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger using the shared configuration."""
    return logging.getLogger(name)
