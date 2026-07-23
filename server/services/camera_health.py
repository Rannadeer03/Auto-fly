"""Pure, thread-free helpers for camera health monitoring.

Kept separate from CameraService so the detection logic is unit-testable
without spinning up a capture thread.
"""
from __future__ import annotations

from typing import Optional

import numpy as np


class FrameFreezeDetector:
    """Flags a camera as frozen once it publishes the same frame bytes for
    too many consecutive reads. A live sensor's frames always differ by at
    least noise, so exact repeats mean the driver/USB stopped updating the
    buffer even though cv2.VideoCapture.read() keeps returning ok=True."""

    def __init__(self, threshold: int) -> None:
        self._threshold = threshold
        self._prev: Optional[np.ndarray] = None
        self._repeat_count = 0

    def update(self, frame: np.ndarray) -> bool:
        """Feed one new frame. Returns True once the threshold is reached."""
        if self._prev is not None and np.array_equal(frame, self._prev):
            self._repeat_count += 1
        else:
            self._repeat_count = 0
        self._prev = frame
        return self._repeat_count >= self._threshold

    def reset(self) -> None:
        self._prev = None
        self._repeat_count = 0

    @property
    def repeat_count(self) -> int:
        return self._repeat_count
