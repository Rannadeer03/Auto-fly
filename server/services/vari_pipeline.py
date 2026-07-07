"""Real-time VARI (Visible Atmospherically Resistant Index) processing
pipeline.

    Camera Frame -> FrameSynchronizer -> VARI Processor -> Threshold ->
    Morphological Cleanup -> Overlay Generator -> VARI Video Writer

Reuses the existing camera pipeline (services/camera_service.py) exactly the
way services/recording_service.py already does — reading the latest
published frame, never touching the capture device itself — and the
existing services/frame_synchronizer.py to associate telemetry with each
frame it processes. No tracking, anomaly IDs, database, or AI/ML model is
involved: this is pixel-level vegetation-index math plus lightweight OpenCV
morphology and a visualization overlay.

VariPipelineWorker runs on its own background thread, paced independently
of both the camera's native frame rate and the mission runner's monitor
loop, so a slow frame (or a Pi 5 CPU spike) can only ever cost this
pipeline a dropped frame — it can never delay flight operations.
"""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import settings
from services.camera_service import CameraService
from services.frame_synchronizer import FrameSynchronizer
from services.mission_session import MissionSessionContext

logger = logging.getLogger(__name__)

_STATS_WINDOW_SECONDS = 5.0
_FRAME_TIME_WINDOW = 30  # rolling average window, in frames


# ── VARI Processor ───────────────────────────────────────────────────────────

def compute_vari(frame_bgr: np.ndarray) -> np.ndarray:
    """VARI = (G - R) / (G + R - B), normalized to a uint8 0-255 image.

    Divide-by-zero (and near-zero denominators, e.g. a saturated/black
    pixel) is handled by defining VARI as 0 (neutral) wherever the
    denominator is exactly 0, instead of raising or producing inf/NaN.
    """
    frame_f = frame_bgr.astype(np.float32)
    b = frame_f[..., 0]
    g = frame_f[..., 1]
    r = frame_f[..., 2]

    numerator = g - r
    denominator = g + r - b
    vari = np.divide(
        numerator, denominator,
        out=np.zeros_like(numerator),
        where=denominator != 0,
    )

    clip_min, clip_max = settings.VARI_CLIP_MIN, settings.VARI_CLIP_MAX
    vari_clipped = np.clip(vari, clip_min, clip_max)
    normalized = (vari_clipped - clip_min) / (clip_max - clip_min) * 255.0
    return normalized.astype(np.uint8)


# ── Threshold ─────────────────────────────────────────────────────────────────

def apply_threshold(vari_normalized: np.ndarray) -> np.ndarray:
    """Binary vegetation mask (0/255) from the normalized VARI image, using
    configurable low/high bounds — never hardcoded."""
    return cv2.inRange(
        vari_normalized, settings.VARI_THRESHOLD_LOW, settings.VARI_THRESHOLD_HIGH
    )


# ── Morphological Cleanup ────────────────────────────────────────────────────

def apply_morphology(mask: np.ndarray) -> np.ndarray:
    """Opening (removes speckle noise) then closing (fills small holes) with
    a small elliptical kernel — deliberately lightweight for a Pi 5."""
    size = max(1, settings.VARI_MORPH_KERNEL_SIZE)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
    cleaned = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN, kernel,
        iterations=max(0, settings.VARI_MORPH_OPEN_ITERATIONS),
    )
    cleaned = cv2.morphologyEx(
        cleaned, cv2.MORPH_CLOSE, kernel,
        iterations=max(0, settings.VARI_MORPH_CLOSE_ITERATIONS),
    )
    return cleaned


# ── Overlay Generator ─────────────────────────────────────────────────────────

def _grid_coverage(mask: np.ndarray, spacing: int) -> np.ndarray:
    """Vectorized per-cell vegetation coverage (0..1) on a *spacing*-px grid,
    via a single pad + reshape + mean — avoids a per-pixel Python loop."""
    h, w = mask.shape[:2]
    pad_h = (-h) % spacing
    pad_w = (-w) % spacing
    padded = np.pad(mask, ((0, pad_h), (0, pad_w)), mode="constant", constant_values=0)
    rows, cols = padded.shape[0] // spacing, padded.shape[1] // spacing
    blocks = padded.reshape(rows, spacing, cols, spacing)
    return blocks.mean(axis=(1, 3)) / 255.0


def generate_overlay(frame_bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Original frame with semi-transparent circular markers over vegetation
    cells — deliberately not a blocky solid-mask fill, so the underlying RGB
    frame stays readable."""
    spacing = max(1, settings.VARI_OVERLAY_MARKER_SPACING_PX)
    radius = max(1, settings.VARI_OVERLAY_MARKER_RADIUS_PX)
    min_coverage = settings.VARI_OVERLAY_MIN_CELL_COVERAGE
    color = settings.VARI_OVERLAY_COLOR_BGR
    alpha = settings.VARI_OVERLAY_ALPHA

    coverage = _grid_coverage(mask, spacing)
    hit_rows, hit_cols = np.nonzero(coverage >= min_coverage)
    if hit_rows.size == 0:
        return frame_bgr

    h, w = mask.shape[:2]
    layer = frame_bgr.copy()
    for r, c in zip(hit_rows.tolist(), hit_cols.tolist()):
        cy = min(r * spacing + spacing // 2, h - 1)
        cx = min(c * spacing + spacing // 2, w - 1)
        cv2.circle(layer, (cx, cy), radius, color, -1, lineType=cv2.LINE_AA)

    return cv2.addWeighted(layer, alpha, frame_bgr, 1 - alpha, 0)


class VariProcessor:
    """VARI -> Threshold -> Morphological Cleanup, as one call."""

    @staticmethod
    def process(frame_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        vari_normalized = compute_vari(frame_bgr)
        mask = apply_threshold(vari_normalized)
        mask = apply_morphology(mask)
        return vari_normalized, mask


# ── VARI Video Writer / pipeline worker ─────────────────────────────────────

class VariPipelineWorker:
    """Runs the full frame flow on its own background thread, paced at
    settings.VARI_PROCESSING_FPS — deliberately decoupled from the camera's
    native fps and from MissionRunner's monitor loop. Reads the camera's
    already-published latest frame (never a queue of its own), so a slow
    processing tick simply re-reads the newest frame next time — frames are
    dropped gracefully, never queued up, and flight operations are never
    delayed by this thread being busy."""

    def __init__(
        self,
        camera: CameraService,
        frame_sync: FrameSynchronizer,
        output_path: Path,
        session: MissionSessionContext,
    ) -> None:
        self._camera = camera
        self._frame_sync = frame_sync
        self._output_path = output_path
        self._session = session

        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._frames_processed = 0
        self._frames_dropped = 0
        self._frame_times: deque[float] = deque(maxlen=_FRAME_TIME_WINDOW)
        self._processed_ts: deque[float] = deque(maxlen=240)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            logger.warning("VARI pipeline already running; ignoring start()")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="vari-pipeline", daemon=True
        )
        self._thread.start()
        logger.info("VARI pipeline started: %s", self._output_path)

    def stop(self) -> dict:
        """Stop the worker and release the video writer. Returns the final
        performance snapshot (also already reflected in the session)."""
        thread = self._thread
        if thread is not None and thread.is_alive():
            self._stop_event.set()
            thread.join(timeout=10.0)
        self._thread = None
        stats = self._stats_snapshot()
        logger.info(
            "VARI pipeline stopped: %s (%d processed, %d dropped)",
            self._output_path, self._frames_processed, self._frames_dropped,
        )
        return stats

    @property
    def is_active(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Worker thread body ──────────────────────────────────────────────────

    def _run(self) -> None:
        fps = max(0.1, settings.VARI_PROCESSING_FPS)
        interval = 1.0 / fps
        writer: Optional[cv2.VideoWriter] = None
        size: Optional[tuple[int, int]] = None
        next_tick = time.monotonic()

        try:
            while not self._stop_event.is_set():
                frame = self._camera.get_frame()
                processed_this_tick = False

                if frame is not None:
                    h, w = frame.shape[:2]
                    if writer is None:
                        size = (w, h)
                        writer = cv2.VideoWriter(
                            str(self._output_path),
                            cv2.VideoWriter_fourcc(*"mp4v"),
                            fps,
                            size,
                        )
                        if not writer.isOpened():
                            logger.error(
                                "VARI VideoWriter failed to open %s", self._output_path
                            )
                            return

                    if (w, h) == size:
                        t0 = time.perf_counter()
                        # Frame -> FrameSynchronizer -> VARI Processor ->
                        # Threshold -> Morphological Cleanup -> Overlay.
                        self._frame_sync.sync()
                        vari_normalized, mask = VariProcessor.process(frame)
                        overlay = generate_overlay(frame, mask)
                        writer.write(overlay)

                        frame_time = time.perf_counter() - t0
                        now = time.monotonic()
                        self._frames_processed += 1
                        self._frame_times.append(frame_time)
                        self._processed_ts.append(now)
                        self._update_session_stats()
                        processed_this_tick = True

                if not processed_this_tick:
                    self._frames_dropped += 1

                next_tick += interval
                sleep_for = next_tick - time.monotonic()
                if sleep_for > 0:
                    self._stop_event.wait(sleep_for)
                else:
                    # Fell behind (Pi 5 CPU spike, slow frame) — resync the
                    # schedule instead of processing a backlog of stale frames.
                    next_tick = time.monotonic()
        except Exception:
            logger.exception("VARI pipeline worker crashed")
        finally:
            if writer is not None:
                writer.release()
                logger.info(
                    "VARI video finalised: %s (%d frames)",
                    self._output_path, self._frames_processed,
                )

    def _stats_snapshot(self) -> dict:
        now = time.monotonic()
        recent = [t for t in self._processed_ts if now - t <= _STATS_WINDOW_SECONDS]
        measured_fps = (len(recent) / _STATS_WINDOW_SECONDS) if recent else 0.0
        avg_frame_time_ms = (
            (sum(self._frame_times) / len(self._frame_times)) * 1000.0
            if self._frame_times else 0.0
        )
        return {
            "measured_fps": round(measured_fps, 2),
            "avg_frame_time_ms": round(avg_frame_time_ms, 2),
            "frames_processed": self._frames_processed,
            "frames_dropped": self._frames_dropped,
        }

    def _update_session_stats(self) -> None:
        # Internal only — not exposed via GET /mission/session yet.
        self._session.processing_stats = {
            **self._session.processing_stats,
            "vari": self._stats_snapshot(),
        }
