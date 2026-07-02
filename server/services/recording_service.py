"""Video recording service.

Writes the shared CameraService's published frames to an .mp4 file on a
dedicated thread, paced at the camera's configured fps. Completely
independent from streaming: it shares only the read-only frame pointer with
the WebRTC path, so a streaming failure never interrupts a recording (and
vice versa).

If the camera drops out mid-recording, the recorder keeps running and
resumes writing frames as soon as the camera reconnects — the file stays
open and the recording survives the outage.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Optional

import cv2

from config import settings
from services.camera_service import CameraService, camera_service

logger = logging.getLogger(__name__)


class RecordingService:
    """Records camera frames to an mp4 file on a background thread."""

    def __init__(self, camera: CameraService) -> None:
        self._camera = camera
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._output_path: Optional[Path] = None
        self._frames_written = 0
        self._started_at: Optional[float] = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def start(self, output_path: Path) -> bool:
        """Begin recording to *output_path*. Returns False if already recording."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                logger.warning("Recording already in progress (%s)", self._output_path)
                return False

            output_path.parent.mkdir(parents=True, exist_ok=True)
            self._output_path = output_path
            self._frames_written = 0
            self._started_at = time.monotonic()
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run, name="video-recorder", daemon=True
            )
            self._thread.start()

        logger.info("Recording started: %s", output_path)
        return True

    def stop(self) -> Optional[Path]:
        """Stop recording. Returns the finished file path, or None if idle."""
        with self._lock:
            thread = self._thread
            path = self._output_path
        if thread is None or not thread.is_alive():
            return None

        self._stop_event.set()
        thread.join(timeout=10.0)
        with self._lock:
            self._thread = None
        logger.info("Recording stopped: %s (%d frames)", path, self._frames_written)
        return path

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def get_status(self) -> dict:
        with self._lock:
            recording = self._thread is not None and self._thread.is_alive()
            return {
                "recording": recording,
                "output_path": str(self._output_path) if recording and self._output_path else None,
                "frames_written": self._frames_written if recording else 0,
                "elapsed_seconds": (
                    round(time.monotonic() - self._started_at, 1)
                    if recording and self._started_at
                    else 0.0
                ),
            }

    # ── Recorder thread body ───────────────────────────────────────────────────

    def _run(self) -> None:
        fps = max(1, settings.CAMERA_FPS)
        interval = 1.0 / fps
        writer: Optional[cv2.VideoWriter] = None
        size: Optional[tuple[int, int]] = None
        next_frame_time = time.monotonic()

        try:
            while not self._stop_event.is_set():
                frame = self._camera.get_frame()
                if frame is not None:
                    h, w = frame.shape[:2]
                    if writer is None:
                        # Open the writer with the actual frame size — the camera
                        # driver may not honour the configured resolution exactly.
                        size = (w, h)
                        writer = cv2.VideoWriter(
                            str(self._output_path),
                            cv2.VideoWriter_fourcc(*"mp4v"),
                            fps,
                            size,
                        )
                        if not writer.isOpened():
                            logger.error(
                                "VideoWriter failed to open %s", self._output_path
                            )
                            return
                    if (w, h) == size:
                        writer.write(frame)
                        with self._lock:
                            self._frames_written += 1

                next_frame_time += interval
                sleep_for = next_frame_time - time.monotonic()
                if sleep_for > 0:
                    self._stop_event.wait(sleep_for)
                else:
                    # Fell behind (slow SD card, CPU spike) — reset the schedule
                    # instead of writing a burst of catch-up frames.
                    next_frame_time = time.monotonic()
        except Exception:
            logger.exception("Recorder thread crashed")
        finally:
            if writer is not None:
                writer.release()
                logger.info(
                    "Video file finalised: %s (%d frames)",
                    self._output_path, self._frames_written,
                )


# Module-level singleton
recording_service = RecordingService(camera_service)
