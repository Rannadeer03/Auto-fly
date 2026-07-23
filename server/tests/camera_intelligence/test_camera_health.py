"""Unit tests for services/camera_health.py FrameFreezeDetector."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from services.camera_health import FrameFreezeDetector


def run_tests() -> None:
    failures = []
    rng = np.random.default_rng(42)

    # Varying frames should never trip the detector.
    detector = FrameFreezeDetector(threshold=5)
    tripped = False
    for _ in range(50):
        frame = rng.integers(0, 255, size=(64, 64, 3), dtype=np.uint8)
        if detector.update(frame):
            tripped = True
    if tripped:
        failures.append("Detector tripped on genuinely varying frames.")

    # Identical frames repeated past the threshold must trip it.
    detector = FrameFreezeDetector(threshold=5)
    frozen_frame = np.full((64, 64, 3), 100, dtype=np.uint8)
    results = [detector.update(frozen_frame.copy()) for _ in range(6)]
    if not any(results):
        failures.append("Detector never tripped on 6 identical frames with threshold=5.")
    if results[0] is True:
        failures.append("Detector tripped on the very first frame (no prior to compare against).")

    # A fresh frame after a freeze must reset the streak.
    detector = FrameFreezeDetector(threshold=3)
    same = np.zeros((32, 32, 3), dtype=np.uint8)
    detector.update(same.copy())
    detector.update(same.copy())
    different = np.ones((32, 32, 3), dtype=np.uint8)
    detector.update(different)
    if detector.repeat_count != 0:
        failures.append(f"Repeat streak did not reset after a new frame: {detector.repeat_count}")

    print(f"Completed camera_health checks. Failures: {len(failures)}")
    if failures:
        print("\n".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
