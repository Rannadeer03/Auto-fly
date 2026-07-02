"""Application-wide configuration.

Every configurable value lives here — nothing is hardcoded elsewhere.
Values are resolved in priority order:

    1. process environment variables
    2. a `.env` file next to this module (server/.env, optional)
    3. the defaults below

deploy/install.sh reads the Wi-Fi values through this module, so `.env`
overrides apply to deployment too.
"""
import os
import platform
from pathlib import Path

BASE_DIR = Path(__file__).parent

_IS_LINUX = platform.system() == "Linux"


def _load_dotenv(path: Path) -> None:
    """Load KEY=VALUE lines from *path* into os.environ (no overwrite).

    Minimal parser — comments (#) and blank lines ignored, optional quotes
    stripped. Process environment variables always win.
    """
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(BASE_DIR / ".env")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class Settings:
    # ── Wi-Fi (applied by deploy/install.sh via NetworkManager) ────────────────
    WIFI_SSID: str = os.environ.get("WIFI_SSID", "Coconut_ufi_97233")
    WIFI_PASSWORD: str = os.environ.get("WIFI_PASSWORD", "1234567890")

    # ── MAVLink / Pixhawk (UART) ───────────────────────────────────────────────
    # Raspberry Pi 5 GPIO UART (pins 8/10) is /dev/serial0 → Pixhawk TELEM port.
    # On non-Linux development machines "auto" scans USB ports instead.
    MAVLINK_PORT: str = os.environ.get(
        "MAVLINK_PORT", "/dev/serial0" if _IS_LINUX else "auto"
    )
    MAVLINK_BAUD: int = int(os.environ.get("MAVLINK_BAUD", "57600"))
    # Pixhawk 2.4.8 can take 15+ seconds to boot and send first heartbeat.
    MAVLINK_TIMEOUT: float = float(os.environ.get("MAVLINK_TIMEOUT", "15.0"))
    HEARTBEAT_TIMEOUT: float = float(os.environ.get("HEARTBEAT_TIMEOUT", "5.0"))

    # Automatic connect at startup + automatic reconnect when the link drops.
    DRONE_AUTO_CONNECT: bool = _env_bool("DRONE_AUTO_CONNECT", True)
    DRONE_AUTO_CONNECT_RETRY_S: float = float(os.environ.get("DRONE_AUTO_CONNECT_RETRY_S", "5.0"))
    # If connected but no heartbeat for this long, tear down and reconnect.
    LINK_STALE_S: float = float(os.environ.get("LINK_STALE_S", "10.0"))

    # Set DEBUG_MAVLINK=1 to log every MAVLink packet sent and received.
    DEBUG_MAVLINK: bool = _env_bool("DEBUG_MAVLINK", False)

    # ── Safety thresholds ──────────────────────────────────────────────────────
    MIN_BATTERY_VOLTAGE: float = float(os.environ.get("MIN_BATTERY_VOLTAGE", "22.2"))
    MIN_BATTERY_PERCENT: int = int(os.environ.get("MIN_BATTERY_PERCENT", "20"))
    MIN_GPS_SATELLITES: int = int(os.environ.get("MIN_GPS_SATELLITES", "6"))
    REQUIRED_GPS_FIX: int = int(os.environ.get("REQUIRED_GPS_FIX", "3"))

    # ── Camera ─────────────────────────────────────────────────────────────────
    # "auto" scans /dev/video* (Linux) and falls back to index 0.
    CAMERA_DEVICE: str = os.environ.get("CAMERA_DEVICE", "auto")
    CAMERA_WIDTH: int = int(os.environ.get("CAMERA_WIDTH", "1280"))
    CAMERA_HEIGHT: int = int(os.environ.get("CAMERA_HEIGHT", "720"))
    CAMERA_FPS: int = int(os.environ.get("CAMERA_FPS", "30"))
    CAMERA_MJPEG: bool = _env_bool("CAMERA_MJPEG", True)
    # Lens field of view — used for mapping footprint / overlap calculations.
    CAMERA_HFOV_DEG: float = float(os.environ.get("CAMERA_HFOV_DEG", "62.2"))
    CAMERA_VFOV_DEG: float = float(os.environ.get("CAMERA_VFOV_DEG", "48.8"))

    # ── Mission automation ─────────────────────────────────────────────────────
    # Continuous photo capture during flight for mapping.
    #   "distance" — one photo every PHOTO_DISTANCE_M metres of travel
    #   "time"     — one photo every PHOTO_INTERVAL_S seconds
    PHOTO_CAPTURE_MODE: str = os.environ.get("PHOTO_CAPTURE_MODE", "distance")
    PHOTO_DISTANCE_M: float = float(os.environ.get("PHOTO_DISTANCE_M", "10.0"))
    PHOTO_INTERVAL_S: float = float(os.environ.get("PHOTO_INTERVAL_S", "2.0"))
    # Only capture photos while airborne in AUTO (skip taxi/RTL descent photos).
    CAPTURE_ONLY_IN_AUTO: bool = _env_bool("CAPTURE_ONLY_IN_AUTO", True)
    # Record video during missions (optional per spec).
    RECORDING_ENABLED: bool = _env_bool("RECORDING_ENABLED", True)
    # Telemetry sample interval during a mission (seconds).
    TELEMETRY_LOG_INTERVAL_S: float = float(os.environ.get("TELEMETRY_LOG_INTERVAL_S", "1.0"))

    # ── Mission planning defaults (exposed to the frontend via GET /config) ───
    DEFAULT_ALTITUDE_M: float = float(os.environ.get("DEFAULT_ALTITUDE_M", "30.0"))
    DEFAULT_SPEED_MS: float = float(os.environ.get("DEFAULT_SPEED_MS", "5.0"))
    DEFAULT_SIDE_OVERLAP_PCT: float = float(os.environ.get("DEFAULT_SIDE_OVERLAP_PCT", "65.0"))
    DEFAULT_FRONT_OVERLAP_PCT: float = float(os.environ.get("DEFAULT_FRONT_OVERLAP_PCT", "75.0"))
    DEFAULT_GRID_ANGLE_DEG: float = float(os.environ.get("DEFAULT_GRID_ANGLE_DEG", "0.0"))

    # ── Storage ────────────────────────────────────────────────────────────────
    MISSIONS_DIR: Path = Path(os.environ.get("MISSIONS_DIR", str(BASE_DIR / "missions")))

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
