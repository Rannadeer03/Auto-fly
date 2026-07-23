"""Pre-flight camera validation.

Gates AUTO mode (mavlink/health.py:HealthChecker.check_auto_ready): captures
a validation burst from the already-running CameraService, scores every
frame, and requires the best one to clear the configured sharpness
confidence threshold before the mission is allowed to start. Retries the
whole burst up to CAMERA_VALIDATION_RETRY_LIMIT times (e.g. lets a
still-focusing autofocus settle) before failing.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from config import settings
from services.camera_service import camera_service
from services.image_quality import QualityScore, score_frame

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    passed: bool
    frames_evaluated: int
    best_score: Optional[QualityScore]
    reason: str


def _collect_burst(frame_count: int) -> list:
    """Grab up to *frame_count* distinct published frames, waiting briefly
    for each to be genuinely new (not the same publish as the last grab)."""
    frames = []
    last_ts: Optional[float] = None
    deadline = time.monotonic() + settings.CAMERA_VALIDATION_FRAME_WAIT_S * frame_count
    while len(frames) < frame_count and time.monotonic() < deadline:
        frame, ts = camera_service.get_frame_with_ts()
        if frame is not None and ts != last_ts:
            frames.append(frame)
            last_ts = ts
            continue
        time.sleep(0.05)
    return frames


def validate_camera() -> ValidationResult:
    if not settings.CAMERA_VALIDATION_ENABLED:
        return ValidationResult(True, 0, None, "Camera validation disabled by configuration.")

    if not camera_service.is_healthy:
        return ValidationResult(False, 0, None, "Camera not healthy — no frames available.")

    attempts = settings.CAMERA_VALIDATION_RETRY_LIMIT + 1
    best_overall: Optional[QualityScore] = None
    frames_evaluated = 0

    for attempt in range(1, attempts + 1):
        frames = _collect_burst(settings.CAMERA_VALIDATION_FRAME_COUNT)
        if not frames:
            logger.warning("Camera validation attempt %d/%d: no frames captured.", attempt, attempts)
            continue

        scores = [score_frame(f) for f in frames]
        frames_evaluated += len(scores)
        best = max(scores, key=lambda s: s.confidence)
        if best_overall is None or best.confidence > best_overall.confidence:
            best_overall = best

        if best.passed:
            logger.info(
                "Camera validation passed on attempt %d/%d: confidence=%.3f (%d frames).",
                attempt, attempts, best.confidence, len(scores),
            )
            return ValidationResult(True, frames_evaluated, best, "Validation passed.")

        logger.warning(
            "Camera validation attempt %d/%d failed: best confidence=%.3f < threshold=%.3f",
            attempt, attempts, best.confidence, settings.QUALITY_CONFIDENCE_THRESHOLD,
        )

    reason = (
        f"Best confidence {best_overall.confidence:.3f} below threshold "
        f"{settings.QUALITY_CONFIDENCE_THRESHOLD:.3f} after {attempts} attempt(s)."
        if best_overall is not None
        else "No frames were captured during validation."
    )
    return ValidationResult(False, frames_evaluated, best_overall, reason)
