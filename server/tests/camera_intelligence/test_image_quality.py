"""Unit tests for services/image_quality.py sharpness scoring.

Standalone script (matches tests/autonomous_pipeline/test_end_to_end.py
convention — no pytest infra in this repo). Run directly:
    python3 tests/camera_intelligence/test_image_quality.py
"""
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from services.image_quality import score_frame, variance_of_laplacian


def make_sharp_frame(size: int = 480) -> np.ndarray:
    """High-frequency checkerboard — unambiguously "in focus"."""
    frame = np.zeros((size, size, 3), dtype=np.uint8)
    step = 8
    for y in range(0, size, step):
        for x in range(0, size, step):
            if ((x // step) + (y // step)) % 2 == 0:
                frame[y : y + step, x : x + step] = 255
    return frame


def make_blurred_frame(sharp: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(sharp, (25, 25), sigmaX=12)


def make_flat_frame(size: int = 480) -> np.ndarray:
    """Perfectly uniform — no edges at all, the degenerate blur case."""
    return np.full((size, size, 3), 128, dtype=np.uint8)


def run_tests() -> None:
    failures = []

    sharp = make_sharp_frame()
    blurred = make_blurred_frame(sharp)
    flat = make_flat_frame()

    sharp_score = score_frame(sharp)
    blurred_score = score_frame(blurred)
    flat_score = score_frame(flat)

    if not (sharp_score.laplacian > blurred_score.laplacian > flat_score.laplacian):
        failures.append(
            f"Laplacian ordering violated: sharp={sharp_score.laplacian:.2f} "
            f"blurred={blurred_score.laplacian:.2f} flat={flat_score.laplacian:.2f}"
        )
    if not (sharp_score.confidence > blurred_score.confidence):
        failures.append(
            f"Confidence ordering violated: sharp={sharp_score.confidence:.3f} "
            f"blurred={blurred_score.confidence:.3f}"
        )
    if not sharp_score.passed:
        failures.append(f"Sharp checkerboard failed quality threshold: {sharp_score.confidence:.3f}")
    if flat_score.passed:
        failures.append("Flat/edgeless frame incorrectly passed quality threshold.")
    if not (0.0 <= sharp_score.confidence <= 1.0):
        failures.append(f"Confidence out of [0,1] range: {sharp_score.confidence}")

    # Metric sanity in isolation
    if variance_of_laplacian(cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY)) != 0.0:
        failures.append("Flat frame should have exactly zero Laplacian variance.")

    d = sharp_score.as_dict()
    for key in ("sharpness_laplacian", "quality_confidence", "quality_passed"):
        if key not in d:
            failures.append(f"QualityScore.as_dict() missing key: {key}")

    print(f"Completed image_quality checks. Failures: {len(failures)}")
    if failures:
        print("\n".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
