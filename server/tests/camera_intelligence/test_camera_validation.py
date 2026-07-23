"""Unit tests for services/camera_validation.py pre-flight validation gate.

Drives the real validate_camera() logic against a stubbed camera_service
singleton (no real camera hardware needed) — this is exactly the gate wired
into mavlink/health.py:HealthChecker.check_auto_ready, so these prove the
"mission must never start on a bad/blurry camera" requirement.
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from config import settings
from services import camera_validation
from services.camera_service import camera_service


def make_sharp_frame(size: int = 480) -> np.ndarray:
    frame = np.zeros((size, size, 3), dtype=np.uint8)
    step = 8
    for y in range(0, size, step):
        for x in range(0, size, step):
            if ((x // step) + (y // step)) % 2 == 0:
                frame[y : y + step, x : x + step] = 255
    return frame


def make_blurred_frame(sharp: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(sharp, (31, 31), sigmaX=15)


class _FakeFrameSource:
    """Every call returns a fresh (frame, ts) pair so _collect_burst never
    has to actually sleep waiting for a "new" frame."""

    def __init__(self, frame: np.ndarray) -> None:
        self.frame = frame
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.frame, float(self.calls)


def run_tests() -> None:
    failures = []
    original_get_frame_with_ts = camera_service.get_frame_with_ts
    original_healthy = camera_service._healthy
    original_validation_enabled = settings.CAMERA_VALIDATION_ENABLED
    original_frame_count = settings.CAMERA_VALIDATION_FRAME_COUNT
    original_retry_limit = settings.CAMERA_VALIDATION_RETRY_LIMIT
    original_frame_wait = settings.CAMERA_VALIDATION_FRAME_WAIT_S

    try:
        settings.CAMERA_VALIDATION_ENABLED = True
        settings.CAMERA_VALIDATION_FRAME_COUNT = 3
        settings.CAMERA_VALIDATION_RETRY_LIMIT = 1
        settings.CAMERA_VALIDATION_FRAME_WAIT_S = 1.0

        # Unhealthy camera must fail fast, without even attempting a burst.
        camera_service._healthy = False
        result = camera_validation.validate_camera()
        if result.passed:
            failures.append("Validation passed despite camera reporting unhealthy.")
        if "not healthy" not in result.reason.lower():
            failures.append(f"Unexpected failure reason for unhealthy camera: {result.reason}")

        # Healthy camera, sharp frames -> must pass.
        camera_service._healthy = True
        sharp = make_sharp_frame()
        camera_service.get_frame_with_ts = _FakeFrameSource(sharp)
        result = camera_validation.validate_camera()
        if not result.passed:
            failures.append(f"Validation failed on sharp frames: {result.reason}")
        if result.best_score is None or not result.best_score.passed:
            failures.append("Validation passed but best_score.passed is falsy.")

        # Healthy camera, persistently blurred frames -> must fail after retries.
        blurred = make_blurred_frame(sharp)
        camera_service.get_frame_with_ts = _FakeFrameSource(blurred)
        result = camera_validation.validate_camera()
        if result.passed:
            failures.append("Validation incorrectly passed on persistently blurred frames.")
        expected_attempts = settings.CAMERA_VALIDATION_RETRY_LIMIT + 1
        expected_frames = expected_attempts * settings.CAMERA_VALIDATION_FRAME_COUNT
        if result.frames_evaluated != expected_frames:
            failures.append(
                f"frames_evaluated={result.frames_evaluated}, expected {expected_frames} "
                f"({expected_attempts} attempts x {settings.CAMERA_VALIDATION_FRAME_COUNT} frames)."
            )

        # Disabled validation must short-circuit to a pass with no frames touched.
        settings.CAMERA_VALIDATION_ENABLED = False
        result = camera_validation.validate_camera()
        if not result.passed or result.frames_evaluated != 0:
            failures.append("Disabled validation did not short-circuit to a no-op pass.")

    finally:
        camera_service.get_frame_with_ts = original_get_frame_with_ts
        camera_service._healthy = original_healthy
        settings.CAMERA_VALIDATION_ENABLED = original_validation_enabled
        settings.CAMERA_VALIDATION_FRAME_COUNT = original_frame_count
        settings.CAMERA_VALIDATION_RETRY_LIMIT = original_retry_limit
        settings.CAMERA_VALIDATION_FRAME_WAIT_S = original_frame_wait

    print(f"Completed camera_validation checks. Failures: {len(failures)}")
    if failures:
        print("\n".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
