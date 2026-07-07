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
from typing import Optional

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
    # TEMP DEBUG — set LOG_TELEMETRY_RX=1 to log every received HEARTBEAT,
    # GPS_RAW_INT, GLOBAL_POSITION_INT, and MISSION_CURRENT at INFO level, to
    # compare live hardware telemetry against what QGroundControl shows.
    # Remove this flag and its call sites once hardware telemetry is confirmed.
    LOG_TELEMETRY_RX: bool = _env_bool("LOG_TELEMETRY_RX", False)

    # Requested via REQUEST_DATA_STREAM right after connecting — without this,
    # ArduPilot sends only HEARTBEAT on a link; GPS/position/status telemetry
    # requires an explicit stream request (every GCS, including QGroundControl,
    # sends this on connect).
    TELEMETRY_STREAM_RATE_HZ: int = int(os.environ.get("TELEMETRY_STREAM_RATE_HZ", "4"))

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
    # Fixed camera mounting angle in degrees from horizontal (-90 = straight
    # down / nadir). There is no gimbal on this rig, so this is a static
    # per-mission descriptive value recorded into each photo's metadata, not
    # something measured dynamically per shot.
    CAMERA_PITCH_DEG: float = float(os.environ.get("CAMERA_PITCH_DEG", "-90.0"))

    # ── Mission automation ─────────────────────────────────────────────────────
    # Top-level capture strategy for survey missions:
    #   "hover"      — mandatory Position Hold at every survey waypoint, then
    #                  capture exactly one photo, then continue (default —
    #                  services/capture_strategies.py:HoverCaptureStrategy)
    #   "continuous" — drone never stops; photos are triggered by distance or
    #                  time while flying (services/capture_strategies.py:
    #                  ContinuousCaptureStrategy). Reserved for future use.
    CAPTURE_STRATEGY: str = os.environ.get("CAPTURE_STRATEGY", "hover")
    # Hold duration (seconds) ArduCopter loiters at each capture waypoint,
    # applied as a dedicated MAV_CMD_NAV_LOITER_TIME mission item inserted
    # after the waypoint (see services/mission_enrichment.py).
    HOVER_HOLD_TIME_S: float = float(os.environ.get("HOVER_HOLD_TIME_S", "2.0"))
    # A capture waypoint must be within this many metres of its planned
    # position (great-circle distance) before the hover/capture sequence is
    # allowed to start — belt-and-suspenders alongside ArduPilot's own
    # MISSION_ITEM_REACHED / acceptance-radius behaviour.
    WAYPOINT_RADIUS_M: float = float(os.environ.get("WAYPOINT_RADIUS_M", "2.0"))
    # A capture waypoint must be within this many metres of its planned
    # relative altitude before the hover/capture sequence is allowed to start.
    ALTITUDE_TOLERANCE_M: float = float(os.environ.get("ALTITUDE_TOLERANCE_M", "2.0"))
    # Maximum distance (metres) between consecutive capture waypoints before
    # mission_enrichment.py inserts intermediate waypoints along the leg.
    # None (default) derives it from the camera footprint at the mission's
    # flight altitude, matching grid_planner's own photo spacing.
    MAX_WAYPOINT_SPACING_M: Optional[float] = (
        float(os.environ["MAX_WAYPOINT_SPACING_M"])
        if os.environ.get("MAX_WAYPOINT_SPACING_M")
        else None
    )

    # Continuous-mode capture sub-settings (only used when
    # CAPTURE_STRATEGY == "continuous").
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
    # Saved, reusable mission *plans* (pre-flight — polygon + params + the
    # generated waypoints), distinct from MISSIONS_DIR's post-flight session
    # archives (photos/video/logs from a completed flight).
    MISSION_LIBRARY_DIR: Path = Path(
        os.environ.get("MISSION_LIBRARY_DIR", str(BASE_DIR / "mission_library"))
    )

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

    # ── HTTPS (self-signed) ─────────────────────────────────────────────────────
    # Browsers only expose the Geolocation API in a "secure context" — HTTPS,
    # or http://localhost — so a plain-HTTP LAN address like http://<pi-ip>:8000
    # (the normal way this app is reached from a laptop) silently blocks "My
    # Location" with no prompt at all. deploy/generate-cert.sh creates a
    # self-signed cert/key here (regenerated automatically if the Pi's LAN IP
    # changes); deploy/start.sh serves HTTPS on the same port whenever both
    # files are present, and falls back to plain HTTP otherwise (e.g. local
    # dev, where a self-signed cert buys nothing since localhost is already a
    # secure context).
    SSL_DIR: Path = BASE_DIR / "deploy" / "certs"
    SSL_CERTFILE: Path = SSL_DIR / "dronai.crt"
    SSL_KEYFILE: Path = SSL_DIR / "dronai.key"

    # ── Mission estimation constants ───────────────────────────────────────────
    DEFAULT_CRUISE_SPEED_MS: float = 5.0
    DEFAULT_BATTERY_CAPACITY_MAH: float = 16000.0
    CRUISE_CURRENT_AMPS: float = 20.0

    # ── Vegetation analysis (Phase 3 — VARI pipeline) ──────────────────────────
    # Frame Synchronizer
    # Maximum number of synchronized frames held in the pipeline queue before
    # old frames are discarded.  Keep small to avoid stale-frame lag.
    SYNC_QUEUE_MAXLEN: int = int(os.environ.get("SYNC_QUEUE_MAXLEN", "4"))

    # VARI processor
    # Process every N-th camera frame (1 = every frame).  Increase on low-power
    # hardware to reduce CPU load without changing the detection logic.
    VARI_PROCESS_EVERY_N: int = int(os.environ.get("VARI_PROCESS_EVERY_N", "1"))

    # Threshold processor
    # 0.0  → use Otsu adaptive thresholding on a uint8 VARI map (recommended).
    # >0.0 → treat as a fixed VARI threshold (e.g. 0.1 selects pixels where
    #         VARI ≥ 0.1, which corresponds to moderately healthy green canopy).
    VARI_THRESHOLD: float = float(os.environ.get("VARI_THRESHOLD", "0.0"))
    # When Otsu is used, multiply the auto-computed threshold by this factor to
    # bias toward more (< 1.0) or fewer (> 1.0) detected pixels.
    VARI_OTSU_SCALE: float = float(os.environ.get("VARI_OTSU_SCALE", "1.0"))

    # Morphology processor
    # Opening kernel size (px) — removes small noise blobs; must be odd.
    MORPH_OPEN_KERNEL_SIZE: int = int(os.environ.get("MORPH_OPEN_KERNEL_SIZE", "5"))
    # Closing kernel size (px) — fills small holes inside regions; must be odd.
    MORPH_CLOSE_KERNEL_SIZE: int = int(os.environ.get("MORPH_CLOSE_KERNEL_SIZE", "7"))
    MORPH_OPEN_ITERATIONS: int = int(os.environ.get("MORPH_OPEN_ITERATIONS", "2"))
    MORPH_CLOSE_ITERATIONS: int = int(os.environ.get("MORPH_CLOSE_ITERATIONS", "2"))

    # Region extractor — filter thresholds
    # Minimum number of foreground pixels for a region to be kept.
    REGION_MIN_PIXEL_COUNT: int = int(os.environ.get("REGION_MIN_PIXEL_COUNT", "150"))
    # Maximum pixel count; 0 = no upper limit.
    REGION_MAX_PIXEL_COUNT: int = int(os.environ.get("REGION_MAX_PIXEL_COUNT", "0"))
    # Reject a region whose area exceeds this fraction of the full frame area
    # (catches spurious full-frame detections in over-exposed conditions).
    REGION_MAX_AREA_FRACTION: float = float(
        os.environ.get("REGION_MAX_AREA_FRACTION", "0.4")
    )
    # Circularity = 4π·area / perimeter².  Ranges 0…1 (perfect circle = 1).
    # Very low circularity → noise-like elongated slivers → rejected.
    REGION_MIN_CIRCULARITY: float = float(
        os.environ.get("REGION_MIN_CIRCULARITY", "0.05")
    )
    # Pixels within this many pixels of any frame edge are considered "border".
    # A region touching the border is rejected (partial canopy / frame edge
    # artefacts produce unreliable shape features).
    REGION_BORDER_MARGIN_PX: int = int(os.environ.get("REGION_BORDER_MARGIN_PX", "5"))

    # Debug — vegetation pipeline
    # Set DEBUG_VARI=true to write annotated developer frames (contour, centroid,
    # region number, bounding box) as JPEG files under DEBUG_VARI_DIR.
    # NEVER expose this path or its contents through a production API endpoint.
    DEBUG_VARI: bool = _env_bool("DEBUG_VARI", False)
    DEBUG_VARI_DIR: Path = Path(
        os.environ.get("DEBUG_VARI_DIR", str(BASE_DIR / "debug_vari"))
    )

    # ── Multi-frame region tracking (Phase 3D) ─────────────────────────────────
    # Similarity method used to associate regions across consecutive frames.
    #   "centroid"  — Euclidean distance between region centroids (default).
    #                 Fast and robust for nadir-view aerial footage where
    #                 vegetation blobs shift only slightly between frames.
    #   "iou"       — Intersection-over-Union of bounding boxes.
    #                 Better when blobs change size between frames.
    #   "area"      — Ratio of contour areas (min/max ∈ [0,1]).
    #                 Useful as a secondary discriminator for similar-centroid
    #                 regions of very different sizes.
    #   "combined"  — Arithmetic mean of all three normalised scores.
    #                 Requires ALL three individual thresholds to pass.
    TRACKING_SIMILARITY_METHOD: str = os.environ.get(
        "TRACKING_SIMILARITY_METHOD", "centroid"
    )
    # Maximum pixel distance between centroids for a match to be valid.
    # Increase for higher-altitude flight (larger ground movement per frame).
    TRACKING_MAX_CENTROID_DIST_PX: float = float(
        os.environ.get("TRACKING_MAX_CENTROID_DIST_PX", "80.0")
    )
    # Minimum IoU for a match to be valid when using the "iou" or "combined"
    # method.  0.0 accepts any overlap; 1.0 requires a perfect bounding-box match.
    TRACKING_MIN_IOU: float = float(os.environ.get("TRACKING_MIN_IOU", "0.1"))
    # Minimum area similarity (min_area / max_area) for a match when using the
    # "area" or "combined" method.
    TRACKING_MIN_AREA_SIMILARITY: float = float(
        os.environ.get("TRACKING_MIN_AREA_SIMILARITY", "0.3")
    )
    # Number of consecutive frames a track may be unmatched before it
    # transitions from LOST → FINISHED and is permanently removed.
    TRACKING_MAX_FRAMES_MISSING: int = int(
        os.environ.get("TRACKING_MAX_FRAMES_MISSING", "5")
    )
    # Maximum number of Region snapshots kept in each track's history ring.
    # Older entries are discarded (FIFO) when the limit is exceeded.
    TRACKING_MAX_HISTORY_LEN: int = int(
        os.environ.get("TRACKING_MAX_HISTORY_LEN", "30")
    )


    # ── Best Observation Selection (Phase 3E) ──────────────────────────────────
    # When two candidate observations have distance-to-image-center values that
    # differ by less than this many pixels they are considered a "tie" and the
    # tiebreaker ordering (mean_vari → area → earlier timestamp) is applied.
    # Set to 0.0 to use strict minimum-distance selection with no tiebreaker.
    OBS_CENTER_TIE_DIST_PX: float = float(
        os.environ.get("OBS_CENTER_TIE_DIST_PX", "5.0")
    )

    # ── Anomaly Domain Model (Phase 3F) ────────────────────────────────────────
    # Weights and thresholds for computing Anomaly Severity (0.0 to 1.0)
    ANOMALY_SEVERITY_WEIGHT_VARI: float = float(os.environ.get("ANOMALY_SEVERITY_WEIGHT_VARI", "0.6"))
    ANOMALY_SEVERITY_WEIGHT_AREA: float = float(os.environ.get("ANOMALY_SEVERITY_WEIGHT_AREA", "0.4"))
    ANOMALY_SEVERITY_BASE_AREA_PX: float = float(os.environ.get("ANOMALY_SEVERITY_BASE_AREA_PX", "5000.0"))
    
    # Weights and thresholds for computing Anomaly Confidence (0.0 to 1.0)
    ANOMALY_CONF_WEIGHT_FRAMES: float = float(os.environ.get("ANOMALY_CONF_WEIGHT_FRAMES", "0.3"))
    ANOMALY_CONF_WEIGHT_DIST: float = float(os.environ.get("ANOMALY_CONF_WEIGHT_DIST", "0.4"))
    ANOMALY_CONF_WEIGHT_PROJ_ERR: float = float(os.environ.get("ANOMALY_CONF_WEIGHT_PROJ_ERR", "0.3"))
    
    ANOMALY_CONF_MAX_FRAMES: float = float(os.environ.get("ANOMALY_CONF_MAX_FRAMES", "10.0"))
    ANOMALY_CONF_MAX_DIST_PX: float = float(os.environ.get("ANOMALY_CONF_MAX_DIST_PX", "600.0"))
    ANOMALY_CONF_MAX_PROJ_ERR_M: float = float(os.environ.get("ANOMALY_CONF_MAX_PROJ_ERR_M", "10.0"))

    # ── Inspection Mission Generator (Phase 3G) ────────────────────────────────
    MISSION_CANDIDATE_MIN_SEVERITY: float = float(os.environ.get("MISSION_CANDIDATE_MIN_SEVERITY", "0.5"))
    MISSION_CANDIDATE_MIN_CONFIDENCE: float = float(os.environ.get("MISSION_CANDIDATE_MIN_CONFIDENCE", "0.5"))
    MISSION_CANDIDATE_MERGE_RADIUS_M: float = float(os.environ.get("MISSION_CANDIDATE_MERGE_RADIUS_M", "10.0"))
    MISSION_CANDIDATE_HOVER_TIME_SEC: float = float(os.environ.get("MISSION_CANDIDATE_HOVER_TIME_SEC", "10.0"))
    MISSION_CANDIDATE_RTL: bool = _env_bool("MISSION_CANDIDATE_RTL", True)
    MISSION_CANDIDATE_INSPECTION_ALTITUDE_M: float = float(os.environ.get("MISSION_CANDIDATE_INSPECTION_ALTITUDE_M", "10.0"))

settings = Settings()


