"""MorphologyProcessor — noise suppression via morphological open→close.

Pipeline (applied in this order):
    1. Opening  (erosion then dilation) — removes isolated noise pixels and
       small speckles smaller than the structuring element.
    2. Closing  (dilation then erosion) — fills small holes inside connected
       vegetation blobs, producing smoother, more compact regions.

Both kernel sizes and iteration counts are read from `settings` at call time:

    MORPH_OPEN_KERNEL_SIZE   — side of the square structuring element for opening
    MORPH_OPEN_ITERATIONS    — number of opening passes
    MORPH_CLOSE_KERNEL_SIZE  — side of the square structuring element for closing
    MORPH_CLOSE_ITERATIONS   — number of closing passes

All kernel sizes must be positive and odd (checked at call time with a helpful
error rather than silently rounding — this catches misconfigured .env values
before they cause subtle shape distortions downstream).

The processor is stateless; kernel objects are re-built on each call from
settings so that live configuration reloads take effect without restarting.
"""

from __future__ import annotations

import cv2
import numpy as np

from config import settings


class MorphologyProcessor:
    """Noise suppression via morphological open then close.

    Stateless — rebuilds structuring elements from settings on every call.
    """

    def process(self, mask: np.ndarray) -> np.ndarray:
        """Apply morphological opening followed by closing to *mask*.

        Parameters
        ----------
        mask:
            uint8 binary image (0/255), shape (H, W), as produced by
            ThresholdProcessor.

        Returns
        -------
        np.ndarray
            Cleaned uint8 binary mask, same shape as input.

        Raises
        ------
        ValueError
            If either kernel size setting is not a positive odd integer.
        """
        if mask.ndim != 2:
            raise ValueError(
                f"Expected a 2-D binary mask, got shape {mask.shape}"
            )

        open_k = settings.MORPH_OPEN_KERNEL_SIZE
        close_k = settings.MORPH_CLOSE_KERNEL_SIZE

        _validate_kernel_size(open_k, "MORPH_OPEN_KERNEL_SIZE")
        _validate_kernel_size(close_k, "MORPH_CLOSE_KERNEL_SIZE")

        open_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (open_k, open_k)
        )
        close_kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE, (close_k, close_k)
        )

        # Step 1 — opening: remove noise speckles
        opened = cv2.morphologyEx(
            mask,
            cv2.MORPH_OPEN,
            open_kernel,
            iterations=settings.MORPH_OPEN_ITERATIONS,
        )

        # Step 2 — closing: fill internal holes
        closed = cv2.morphologyEx(
            opened,
            cv2.MORPH_CLOSE,
            close_kernel,
            iterations=settings.MORPH_CLOSE_ITERATIONS,
        )

        return closed


# ── Helpers ────────────────────────────────────────────────────────────────────

def _validate_kernel_size(size: int, name: str) -> None:
    """Raise ValueError if *size* is not a positive odd integer."""
    if size <= 0 or size % 2 == 0:
        raise ValueError(
            f"{name}={size} is invalid; must be a positive odd integer "
            "(e.g. 3, 5, 7).  Check your environment or .env file."
        )
