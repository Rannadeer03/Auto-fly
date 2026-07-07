"""ThresholdProcessor — converts a VARI float32 map to a binary uint8 mask.

Two modes, selected by `VARI_THRESHOLD` in settings:

Fixed threshold (VARI_THRESHOLD > 0.0)
    A pixel is "vegetation" if its VARI value ≥ VARI_THRESHOLD.
    Output: 255 where condition holds, 0 elsewhere.

Otsu adaptive thresholding (VARI_THRESHOLD == 0.0, the default)
    1. Normalise the VARI map to uint8 [0, 255] using the observed min/max
       of the current frame (not fixed limits) so that the full uint8 range
       is always used regardless of scene brightness.
    2. Apply OpenCV's THRESH_BINARY + THRESH_OTSU to find the optimal
       global threshold automatically.
    3. Optionally scale the Otsu threshold by VARI_OTSU_SCALE before
       applying it, letting operators bias toward more or fewer pixels
       without retuning per-scene.

In both modes the output is a uint8 ndarray (same H×W as the input) with
values 0 (background) or 255 (vegetation).
"""

from __future__ import annotations

import cv2
import numpy as np

from config import settings


class ThresholdProcessor:
    """Converts a VARI float32 map to a binary vegetation mask.

    Stateless — all parameters are read from `settings` at call time, so
    changing environment variables and restarting is sufficient to retune.
    """

    def process(self, vari_map: np.ndarray) -> np.ndarray:
        """Threshold a VARI map into a binary mask.

        Parameters
        ----------
        vari_map:
            float32 array of shape (H, W) as produced by VARIProcessor.

        Returns
        -------
        np.ndarray
            uint8 array of shape (H, W) — 255 = vegetation, 0 = background.
        """
        if vari_map.ndim != 2:
            raise ValueError(
                f"Expected a 2-D VARI map, got shape {vari_map.shape}"
            )

        if settings.VARI_THRESHOLD > 0.0:
            return self._fixed_threshold(vari_map)
        return self._otsu_threshold(vari_map)

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _fixed_threshold(vari_map: np.ndarray) -> np.ndarray:
        """Apply a configurable fixed VARI threshold."""
        mask = (vari_map >= settings.VARI_THRESHOLD).astype(np.uint8) * 255
        return mask

    @staticmethod
    def _otsu_threshold(vari_map: np.ndarray) -> np.ndarray:
        """Apply Otsu's method on a uint8-normalised view of the VARI map.

        Normalisation uses the per-frame min/max so that the uint8 range is
        fully utilised regardless of whether the scene is a bright sand flat
        or a dense canopy.

        When the frame has zero variance (all pixels identical, e.g. a solid
        colour calibration target) Otsu produces a threshold of 0; in that
        edge case we return an all-zero mask rather than all-255.
        """
        vmin = float(np.min(vari_map))
        vmax = float(np.max(vari_map))

        if vmax == vmin:
            # Degenerate frame — no variance, no vegetation
            return np.zeros_like(vari_map, dtype=np.uint8)

        # Normalise to [0, 255]
        normalised = ((vari_map - vmin) / (vmax - vmin) * 255.0).astype(np.uint8)

        # Let OpenCV compute the optimal threshold via Otsu
        otsu_thresh_raw, _ = cv2.threshold(
            normalised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )

        # Apply optional scale factor — allows biasing without re-tuning
        scaled_thresh = otsu_thresh_raw * settings.VARI_OTSU_SCALE

        # Re-apply the (possibly scaled) threshold on the uint8 normalised map
        _, mask = cv2.threshold(
            normalised,
            scaled_thresh,
            255,
            cv2.THRESH_BINARY,
        )
        return mask
