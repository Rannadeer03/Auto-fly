"""Typed, environment-overridable configuration.

Why this exists: the spec requires that swapping the USB webcam for the
OV9281, or changing resolution/fps/MJPEG, be a configuration change rather
than a code change. A single typed module is the minimal way to make that
literally true. Every field has a sane default so the service runs with zero
environment setup today, and can be retargeted at flight time via env vars
without touching source.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent


def _env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return int(raw) if raw is not None else default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CameraConfig:
    """Capture parameters for a single video source.

    `device` accepts either a /dev/videoN path (string) or an OpenCV camera
    index (int-like string), since both are valid `cv2.VideoCapture` args.
    """

    device: str = "/dev/video0"
    width: int = 1280
    height: int = 720
    fps: int = 30
    use_mjpeg: bool = True

    @classmethod
    def from_env(cls) -> "CameraConfig":
        return cls(
            device=_env_str("DRONAI_CAMERA_DEVICE", cls.device),
            width=_env_int("DRONAI_CAMERA_WIDTH", cls.width),
            height=_env_int("DRONAI_CAMERA_HEIGHT", cls.height),
            fps=_env_int("DRONAI_CAMERA_FPS", cls.fps),
            use_mjpeg=_env_bool("DRONAI_CAMERA_MJPEG", cls.use_mjpeg),
        )


@dataclass(frozen=True)
class AppConfig:
    """Process-wide settings."""

    host: str = "0.0.0.0"
    port: int = 8000
    log_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "logs")
    camera: CameraConfig = field(default_factory=CameraConfig)

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            host=_env_str("DRONAI_HOST", cls.host),
            port=_env_int("DRONAI_PORT", cls.port),
            log_dir=Path(_env_str("DRONAI_LOG_DIR", str(PROJECT_ROOT / "logs"))),
            camera=CameraConfig.from_env(),
        )


def load_config() -> AppConfig:
    """Single entry point app.py uses to build configuration at startup."""
    return AppConfig.from_env()
