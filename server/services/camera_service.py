"""Threaded USB camera capture service.

Adapted from the Webcam project's backend/services/camera.py.

One background thread owns the `cv2.VideoCapture` exclusively, opens it once,
and publishes the latest decoded frame. Consumers (WebRTC track, recorder,
photo capture, status endpoints) read the published frame without touching
the capture device. If the camera disconnects, the thread automatically
retries opening it with backoff — the service never dies.
"""

from __future__ import annotations

import glob
import logging
import platform
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import settings

logger = logging.getLogger(__name__)

# Reopen backoff schedule: fast first retry, then settle at a 5s cap so a
# genuinely unplugged camera doesn't spam logs or burn CPU.
_REOPEN_BACKOFF_SCHEDULE = (1.0, 2.0, 5.0)
_FPS_WINDOW_SECONDS = 2.0


def detect_camera_device() -> Optional[str]:
    """Return the first USB camera device found, or None.

    Linux (Raspberry Pi): first /dev/video* node.
    macOS (development):  OpenCV index "0" (no /dev/video* nodes exist).
    """
    if platform.system() == "Linux":
        nodes = sorted(glob.glob("/dev/video*"))
        return nodes[0] if nodes else None
    return "0"


def list_camera_devices() -> list[str]:
    """Return all candidate camera device nodes on this system."""
    if platform.system() == "Linux":
        return sorted(glob.glob("/dev/video*"))
    return ["0"]


@dataclass
class FrameStats:
    """Snapshot of capture health, exposed to /camera/status."""

    healthy: bool
    device: str
    measured_fps: float
    frame_count: int
    configured_width: int
    configured_height: int
    configured_fps: int
    last_frame_age_seconds: Optional[float]


class CameraService:
    """Owns one `cv2.VideoCapture` and publishes the latest frame.

    Thread-safety model: the capture thread is the only writer of
    `_latest_frame`. `cv2.read()` always returns a freshly allocated
    `ndarray`, so published frames are never mutated in place — the lock
    only protects the pointer swap.
    """

    def __init__(self) -> None:
        self._capture: Optional[cv2.VideoCapture] = None

        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_frame_ts: Optional[float] = None

        self._frame_timestamps: deque[float] = deque(maxlen=240)
        self._frame_count = 0
        self._healthy = False
        self._active_device: str = settings.CAMERA_DEVICE

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the capture thread. Idempotent — never opens twice."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("CameraService.start() called while already running; ignoring")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="camera-capture", daemon=True
        )
        self._thread.start()
        logger.info(
            "Camera thread started (device=%s, %dx%d@%dfps, mjpeg=%s)",
            settings.CAMERA_DEVICE,
            settings.CAMERA_WIDTH,
            settings.CAMERA_HEIGHT,
            settings.CAMERA_FPS,
            settings.CAMERA_MJPEG,
        )

    def stop(self) -> None:
        """Signal the capture thread to stop and release the device."""
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=5.0)
        if self._thread.is_alive():
            logger.error("Camera capture thread did not stop within timeout")
        self._thread = None
        logger.info("Camera stopped")

    # ── consumer API ───────────────────────────────────────────────────────────

    def get_frame(self) -> Optional[np.ndarray]:
        """Return the most recently captured frame, or None if none yet."""
        with self._lock:
            return self._latest_frame

    def capture_photo(self, path: Path) -> bool:
        """Write the latest frame to *path* as a JPEG. Returns False if no frame."""
        frame = self.get_frame()
        if frame is None:
            logger.warning("Photo capture failed: no camera frame available")
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        ok = cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 92])
        if ok:
            logger.info("Photo captured: %s", path)
        else:
            logger.error("cv2.imwrite failed for %s", path)
        return ok

    def get_stats(self) -> FrameStats:
        now = time.monotonic()
        with self._lock:
            frame_age = (now - self._latest_frame_ts) if self._latest_frame_ts else None
            timestamps = list(self._frame_timestamps)
            healthy = self._healthy
            frame_count = self._frame_count
            device = self._active_device

        recent = [t for t in timestamps if now - t <= _FPS_WINDOW_SECONDS]
        measured_fps = (len(recent) / _FPS_WINDOW_SECONDS) if recent else 0.0

        return FrameStats(
            healthy=healthy,
            device=device,
            measured_fps=round(measured_fps, 1),
            frame_count=frame_count,
            configured_width=settings.CAMERA_WIDTH,
            configured_height=settings.CAMERA_HEIGHT,
            configured_fps=settings.CAMERA_FPS,
            last_frame_age_seconds=frame_age,
        )

    @property
    def is_healthy(self) -> bool:
        with self._lock:
            return self._healthy

    # ── capture thread body ────────────────────────────────────────────────────

    def _run(self) -> None:
        backoff_index = 0
        while not self._stop_event.is_set():
            cap = self._open_capture()
            if cap is None:
                delay = _REOPEN_BACKOFF_SCHEDULE[
                    min(backoff_index, len(_REOPEN_BACKOFF_SCHEDULE) - 1)
                ]
                backoff_index += 1
                self._mark_unhealthy()
                self._stop_event.wait(delay)
                continue

            backoff_index = 0
            self._capture = cap
            self._read_loop(cap)
            self._release_capture(cap)

        if self._capture is not None:
            self._release_capture(self._capture)
            self._capture = None

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        device = settings.CAMERA_DEVICE
        if device == "auto":
            detected = detect_camera_device()
            if detected is None:
                logger.error("No USB camera found (/dev/video*). Will retry.")
                return None
            device = detected

        with self._lock:
            self._active_device = device

        # cv2.VideoCapture wants an int for index-style devices, a str for paths.
        device_arg = int(device) if isinstance(device, str) and device.isdigit() else device

        backend = cv2.CAP_V4L2 if platform.system() == "Linux" else cv2.CAP_ANY
        cap = cv2.VideoCapture(device_arg, backend)
        if not cap.isOpened():
            cap.release()
            logger.error("Failed to open camera device %s", device)
            return None

        if settings.CAMERA_MJPEG:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, settings.CAMERA_FPS)
        # Keep the driver buffer shallow so we always read a recent frame
        # instead of draining a backlog when the consumer is briefly slow.
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        logger.info("Camera device %s opened", device)
        return cap

    def _read_loop(self, cap: cv2.VideoCapture) -> None:
        consecutive_failures = 0
        max_consecutive_failures = 10

        while not self._stop_event.is_set():
            ok, frame = cap.read()
            if not ok or frame is None:
                consecutive_failures += 1
                logger.warning(
                    "Camera read failed (%d/%d consecutive)",
                    consecutive_failures,
                    max_consecutive_failures,
                )
                if consecutive_failures >= max_consecutive_failures:
                    logger.error("Camera appears disconnected; will attempt reopen")
                    self._mark_unhealthy()
                    return
                time.sleep(0.1)
                continue

            consecutive_failures = 0
            now = time.monotonic()
            with self._lock:
                self._latest_frame = frame
                self._latest_frame_ts = now
                self._frame_timestamps.append(now)
                self._frame_count += 1
                self._healthy = True

    def _mark_unhealthy(self) -> None:
        with self._lock:
            self._healthy = False

    def _release_capture(self, cap: cv2.VideoCapture) -> None:
        cap.release()
        logger.info("Camera device released")


def make_placeholder_frame(width: int, height: int, message: str = "NO CAMERA SIGNAL") -> np.ndarray:
    """Generate a black frame with a status message.

    Used by the WebRTC video track when no real frame has been captured yet,
    so a peer connection can still negotiate and display something meaningful.
    """
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(message, font, 1.0, 2)[0]
    origin = ((width - text_size[0]) // 2, (height + text_size[1]) // 2)
    cv2.putText(frame, message, origin, font, 1.0, (0, 0, 255), 2, cv2.LINE_AA)
    return frame


# Module-level singleton — imported by streaming, recording, and mission runner
camera_service = CameraService()
