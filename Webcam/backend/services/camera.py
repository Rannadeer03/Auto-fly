"""Threaded camera capture service.

Why a dedicated thread: `cv2.VideoCapture.read()` blocks on I/O. Running it
on the asyncio event loop (the same loop that drives aiortc/FastAPI) would
stall every WebRTC connection and every HTTP request while waiting on the
camera driver. Instead, one background thread owns the `VideoCapture`
exclusively, opens it exactly once, and publishes the latest decoded frame.
Consumers (the WebRTC track, status endpoints) read that published frame
without ever touching the capture device themselves.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

from backend.config import CameraConfig
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# Reopen backoff schedule: fast first retry, then settle at a 5s cap so a
# genuinely unplugged camera doesn't spam logs or burn CPU.
_REOPEN_BACKOFF_SCHEDULE = (1.0, 2.0, 5.0)
_FPS_WINDOW_SECONDS = 2.0


@dataclass
class FrameStats:
    """Snapshot of capture health, exposed to /api/status."""

    healthy: bool
    measured_fps: float
    frame_count: int
    configured_width: int
    configured_height: int
    configured_fps: int
    last_frame_age_seconds: Optional[float]


class Camera:
    """Owns one `cv2.VideoCapture` and publishes the latest frame.

    Thread-safety model: the capture thread is the only writer of
    `_latest_frame`. `cv2.read()` always returns a freshly allocated
    `ndarray`, so previously published frames are never mutated in place —
    the lock only needs to protect the pointer swap, not a frame copy. This
    keeps `get_frame()` on the hot path allocation-free.
    """

    def __init__(self, config: CameraConfig) -> None:
        self._config = config
        self._capture: Optional[cv2.VideoCapture] = None

        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_frame_ts: Optional[float] = None

        self._frame_timestamps: deque[float] = deque(maxlen=240)
        self._frame_count = 0
        self._healthy = False

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # -- lifecycle ---------------------------------------------------

    def start(self) -> None:
        """Start the capture thread. Idempotent — never opens twice."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("Camera.start() called while already running; ignoring")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="camera-capture", daemon=True
        )
        self._thread.start()
        logger.info(
            "Camera thread started (device=%s, %dx%d@%dfps, mjpeg=%s)",
            self._config.device,
            self._config.width,
            self._config.height,
            self._config.fps,
            self._config.use_mjpeg,
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

    # -- consumer API --------------------------------------------------

    def get_frame(self) -> Optional[np.ndarray]:
        """Return the most recently captured frame, or None if none yet."""
        with self._lock:
            return self._latest_frame

    def get_stats(self) -> FrameStats:
        now = time.monotonic()
        with self._lock:
            frame_age = (now - self._latest_frame_ts) if self._latest_frame_ts else None
            timestamps = list(self._frame_timestamps)
            healthy = self._healthy
            frame_count = self._frame_count

        recent = [t for t in timestamps if now - t <= _FPS_WINDOW_SECONDS]
        measured_fps = (len(recent) / _FPS_WINDOW_SECONDS) if recent else 0.0

        return FrameStats(
            healthy=healthy,
            measured_fps=round(measured_fps, 1),
            frame_count=frame_count,
            configured_width=self._config.width,
            configured_height=self._config.height,
            configured_fps=self._config.fps,
            last_frame_age_seconds=frame_age,
        )

    @property
    def is_healthy(self) -> bool:
        with self._lock:
            return self._healthy

    @property
    def config(self) -> CameraConfig:
        return self._config

    # -- capture thread body --------------------------------------------

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
        device = self._config.device
        # cv2.VideoCapture wants an int for index-style devices, a str for paths.
        device_arg = int(device) if isinstance(device, str) and device.isdigit() else device

        cap = cv2.VideoCapture(device_arg, cv2.CAP_V4L2)
        if not cap.isOpened():
            cap.release()
            logger.error("Failed to open camera device %s", device)
            return None

        if self._config.use_mjpeg:
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._config.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._config.height)
        cap.set(cv2.CAP_PROP_FPS, self._config.fps)
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
        logger.info("Camera device %s released", self._config.device)


def make_placeholder_frame(width: int, height: int, message: str = "NO CAMERA SIGNAL") -> np.ndarray:
    """Generate a black frame with a status message.

    Used by the video track (not this class) when no real frame has ever
    been captured yet, so a peer connection can still negotiate and display
    something meaningful instead of failing to start.
    """
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(message, font, 1.0, 2)[0]
    origin = ((width - text_size[0]) // 2, (height + text_size[1]) // 2)
    cv2.putText(frame, message, origin, font, 1.0, (0, 0, 255), 2, cv2.LINE_AA)
    return frame
