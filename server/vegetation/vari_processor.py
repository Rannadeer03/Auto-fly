"""VARIProcessor — converts a BGR camera frame to a VARI float32 map.

VARI (Visible Atmospherically Resistant Index)
-----------------------------------------------
    VARI = (G − R) / (G + R − B)

VARI is designed for RGB-camera vegetation detection without a near-infrared
band.  Healthy green canopy drives G up and R down, yielding positive VARI
values.  Soil, concrete, and senescent vegetation produce values closer to 0
or negative.

Implementation notes
--------------------
- All arithmetic is performed in float32 to avoid integer saturation.
- Division-by-zero (G + R − B = 0) is handled by substituting 0.0 in those
  pixels via np.where — this is numerically safe and keeps the output in a
  well-defined range.
- Output range is theoretically (−∞, +∞) but in practice ≈ −1…+1 for
  real-world scenes.  Downstream stages (threshold, visualisation) must not
  assume a fixed range.
- The processor is stateless — it holds no references between calls and is
  trivially reusable.
"""

from __future__ import annotations

import numpy as np


class VARIProcessor:
    """Stateless converter: BGR ndarray → VARI float32 map.

    Usage::

        processor = VARIProcessor()
        vari_map = processor.process(bgr_frame)
    """

    def process(self, bgr_image: np.ndarray) -> np.ndarray:
        """Compute the VARI index for every pixel in *bgr_image*.

        Parameters
        ----------
        bgr_image:
            uint8 BGR image as returned by cv2 / CameraService.  Shape
            (H, W, 3).  Must not be empty.

        Returns
        -------
        np.ndarray
            float32 array of shape (H, W) with per-pixel VARI values.
            Values where the denominator is zero are set to 0.0.
        """
        if bgr_image.ndim != 3 or bgr_image.shape[2] != 3:
            raise ValueError(
                f"Expected a 3-channel BGR image, got shape {bgr_image.shape}"
            )

        # Split channels — OpenCV is BGR, so index 0 = Blue, 1 = Green, 2 = Red
        b = bgr_image[:, :, 0].astype(np.float32)
        g = bgr_image[:, :, 1].astype(np.float32)
        r = bgr_image[:, :, 2].astype(np.float32)

        numerator = g - r           # VARI numerator:   G − R
        denominator = g + r - b     # VARI denominator: G + R − B

        # Avoid division-by-zero: use np.errstate to suppress the NumPy
        # RuntimeWarning that fires when numerator/denominator is evaluated
        # on the full array before np.where masks out zero-denominator cells.
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(denominator != 0.0, numerator / denominator, 0.0)

        vari = ratio

        return vari.astype(np.float32)
