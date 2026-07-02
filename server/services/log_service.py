"""
Web log service.

Installs a custom Python logging handler that stores recent log records in a
thread-safe circular buffer so the /logs endpoint can serve them to the UI.
Also writes all records to a rotating file log on disk.
"""
import logging
import logging.handlers
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from config import settings


class _WebLogHandler(logging.Handler):
    """Stores formatted log records in an in-memory deque for the /logs API."""

    def __init__(self, max_entries: int) -> None:
        super().__init__()
        self._buffer: deque[dict] = deque(maxlen=max_entries)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": datetime.fromtimestamp(record.created, tz=timezone.utc)
                      .strftime("%Y-%m-%dT%H:%M:%SZ"),
                "level": record.levelname,
                "logger": record.name,
                "msg": self.format(record),
            }
            with self._lock:
                self._buffer.append(entry)
        except Exception:
            self.handleError(record)

    def get_recent(self, count: int = 200) -> list[dict]:
        with self._lock:
            return list(self._buffer)[-count:]

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()


class LogService:
    """Configures application logging and exposes logs to the web interface."""

    def __init__(self) -> None:
        self._web_handler = _WebLogHandler(max_entries=settings.MAX_WEB_LOG_ENTRIES)
        self._configured = False

    def configure(self) -> None:
        if self._configured:
            return
        self._configured = True

        log_dir = settings.LOG_DIR
        log_dir.mkdir(parents=True, exist_ok=True)

        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        # Web buffer handler
        self._web_handler.setFormatter(formatter)

        # Rotating file handler (10 MB × 5 files)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "missionplanner.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        root = logging.getLogger()
        root.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
        root.addHandler(self._web_handler)
        root.addHandler(file_handler)
        root.addHandler(console_handler)

        # Silence noisy third-party loggers
        logging.getLogger("pymavlink").setLevel(logging.WARNING)
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    def get_recent_logs(self, count: int = 200) -> list[dict]:
        return self._web_handler.get_recent(count)

    def clear_logs(self) -> None:
        self._web_handler.clear()


log_service = LogService()
