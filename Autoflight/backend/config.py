"""Application-wide configuration loaded from environment variables with safe defaults."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent


class Settings:
    # ── MAVLink ────────────────────────────────────────────────────────────────
    # "auto" scans for Pixhawk on /dev/cu.usbmodem* (macOS) or /dev/ttyACM* (Linux).
    # Override with MAVLINK_PORT=/dev/cu.usbmodem14201 etc.
    MAVLINK_PORT: str = os.environ.get("MAVLINK_PORT", "auto")
    MAVLINK_BAUD: int = int(os.environ.get("MAVLINK_BAUD", "57600"))
    # Pixhawk 2.4.8 can take 15+ seconds to boot and send first heartbeat.
    MAVLINK_TIMEOUT: float = float(os.environ.get("MAVLINK_TIMEOUT", "15.0"))
    HEARTBEAT_TIMEOUT: float = float(os.environ.get("HEARTBEAT_TIMEOUT", "5.0"))

    # Set DEBUG_MAVLINK=1 to log every MAVLink packet sent and received.
    DEBUG_MAVLINK: bool = os.environ.get("DEBUG_MAVLINK", "").lower() in ("1", "true", "yes")

    # ── Safety thresholds ──────────────────────────────────────────────────────
    MIN_BATTERY_VOLTAGE: float = float(os.environ.get("MIN_BATTERY_VOLTAGE", "22.2"))
    MIN_BATTERY_PERCENT: int = int(os.environ.get("MIN_BATTERY_PERCENT", "20"))
    MIN_GPS_SATELLITES: int = int(os.environ.get("MIN_GPS_SATELLITES", "6"))
    REQUIRED_GPS_FIX: int = int(os.environ.get("REQUIRED_GPS_FIX", "3"))

    # ── File upload ────────────────────────────────────────────────────────────
    MAX_UPLOAD_BYTES: int = int(os.environ.get("MAX_UPLOAD_SIZE_MB", "10")) * 1024 * 1024
    UPLOAD_DIR: Path = BASE_DIR / "uploads" / "missions"
    ALLOWED_EXTENSIONS: frozenset = frozenset({".waypoints", ".plan"})

    # ── Logging ────────────────────────────────────────────────────────────────
    LOG_DIR: Path = BASE_DIR / "logs"
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
    MAX_WEB_LOG_ENTRIES: int = 500

    # ── Server ─────────────────────────────────────────────────────────────────
    HOST: str = os.environ.get("HOST", "0.0.0.0")
    PORT: int = int(os.environ.get("PORT", "8000"))

    # ── Mission estimation constants ───────────────────────────────────────────
    DEFAULT_CRUISE_SPEED_MS: float = 5.0
    DEFAULT_BATTERY_CAPACITY_MAH: float = 16000.0
    CRUISE_CURRENT_AMPS: float = 20.0


settings = Settings()
