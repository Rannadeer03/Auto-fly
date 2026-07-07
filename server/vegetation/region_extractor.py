"""RegionExtractor — Connected Components → filtered List[Region].

Pipeline
--------
    cleaned_mask (uint8, from MorphologyProcessor)
        │
        ▼
    cv2.connectedComponentsWithStats
        │   Produces N+1 labels (0 = background, 1..N = blobs).
        │   Stats include: left, top, width, height, area (pixel count).
        ▼
    For each blob (label 1..N):
        │
        ├── Extract individual blob mask  (label == i)
        ├── cv2.findContours on blob mask → primary contour
        ├── Compute centroid (image moments)
        ├── Compute area (cv2.contourArea)
        ├── Compute circularity (4π·area / perimeter²)
        ├── Compute mean_vari inside the blob mask
        │
        └── Apply filters (ALL thresholds from settings — no magic numbers):
                pixel_count < REGION_MIN_PIXEL_COUNT            → reject
                REGION_MAX_PIXEL_COUNT > 0 and
                  pixel_count > REGION_MAX_PIXEL_COUNT           → reject
                area / frame_area > REGION_MAX_AREA_FRACTION     → reject
                circularity < REGION_MIN_CIRCULARITY             → reject
                region touches image border within
                  REGION_BORDER_MARGIN_PX pixels                 → reject
        │
        ▼
    Accepted blobs → Region objects with UUID temporary IDs
        │
        ▼
    List[Region]  (may be empty)

Design constraints
------------------
- No tracking, no GPS, no anomaly IDs, no database writes.
- All numeric thresholds come exclusively from `settings`.
- The caller supplies the VARI float32 map so that mean_vari can be
  computed from the same map used for thresholding — no re-computation.
"""

from __future__ import annotations

import logging
import math
import uuid
from typing import List

import cv2
import numpy as np

from config import settings
from vegetation.region_model import Region
from vegetation.synchronized_frame import SynchronizedFrame

logger = logging.getLogger(__name__)


class RegionExtractor:
    """Extracts and filters connected vegetation blobs from a binary mask.

    Stateless — all parameters read from `settings` at call time.
    """

    def extract(
        self,
        sf: SynchronizedFrame,
        cleaned_mask: np.ndarray,
        vari_map: np.ndarray,
    ) -> List[Region]:
        """Extract regions from *cleaned_mask*.

        Parameters
        ----------
        sf:
            The SynchronizedFrame whose image produced this mask.  Used to
            stamp `frame_uuid` and `timestamp` onto each Region.
        cleaned_mask:
            uint8 binary mask (0/255), shape (H, W), from MorphologyProcessor.
        vari_map:
            float32 VARI map (H, W) from VARIProcessor.  Used to compute
            mean_vari for each accepted region.

        Returns
        -------
        List[Region]
            Zero or more Region objects (may be empty if every blob is
            rejected by the configured filters).
        """
        if cleaned_mask.ndim != 2 or cleaned_mask.dtype != np.uint8:
            raise ValueError(
                "cleaned_mask must be a 2-D uint8 array; "
                f"got shape={cleaned_mask.shape} dtype={cleaned_mask.dtype}"
            )
        if vari_map.ndim != 2 or vari_map.dtype != np.float32:
            raise ValueError(
                "vari_map must be a 2-D float32 array; "
                f"got shape={vari_map.shape} dtype={vari_map.dtype}"
            )

        frame_h, frame_w = cleaned_mask.shape
        frame_area = float(frame_h * frame_w)
        margin = settings.REGION_BORDER_MARGIN_PX

        # ── Connected components ───────────────────────────────────────────────
        num_labels, label_map, stats, _ = cv2.connectedComponentsWithStats(
            cleaned_mask, connectivity=8, ltype=cv2.CV_32S
        )
        # num_labels includes label 0 (background); real blobs are 1..num_labels-1

        regions: List[Region] = []

        for label in range(1, num_labels):
            # ── Pixel count (from stats) ───────────────────────────────────────
            pixel_count: int = int(stats[label, cv2.CC_STAT_AREA])

            # Filter: too small
            if pixel_count < settings.REGION_MIN_PIXEL_COUNT:
                logger.debug(
                    "Region label=%d rejected: pixel_count=%d < min=%d",
                    label, pixel_count, settings.REGION_MIN_PIXEL_COUNT,
                )
                continue

            # Filter: too large (only if max is set)
            max_px = settings.REGION_MAX_PIXEL_COUNT
            if max_px > 0 and pixel_count > max_px:
                logger.debug(
                    "Region label=%d rejected: pixel_count=%d > max=%d",
                    label, pixel_count, max_px,
                )
                continue

            # ── Bounding box ───────────────────────────────────────────────────
            x = int(stats[label, cv2.CC_STAT_LEFT])
            y = int(stats[label, cv2.CC_STAT_TOP])
            w = int(stats[label, cv2.CC_STAT_WIDTH])
            h = int(stats[label, cv2.CC_STAT_HEIGHT])
            bounding_box = (x, y, w, h)

            # Filter: touches border
            if _touches_border(x, y, w, h, frame_w, frame_h, margin):
                logger.debug(
                    "Region label=%d rejected: touches image border (margin=%d px)",
                    label, margin,
                )
                continue

            # ── Isolate blob mask & extract contour ───────────────────────────
            blob_mask = (label_map == label).astype(np.uint8) * 255
            contours, _ = cv2.findContours(
                blob_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            if not contours:
                logger.debug("Region label=%d rejected: no contour found", label)
                continue

            # Use the largest contour (should be exactly one, but be defensive)
            contour = max(contours, key=cv2.contourArea)

            # ── Area ──────────────────────────────────────────────────────────
            area = float(cv2.contourArea(contour))

            # Filter: area fraction too large
            if area / frame_area > settings.REGION_MAX_AREA_FRACTION:
                logger.debug(
                    "Region label=%d rejected: area_fraction=%.4f > max=%.4f",
                    label, area / frame_area, settings.REGION_MAX_AREA_FRACTION,
                )
                continue

            # ── Circularity ───────────────────────────────────────────────────
            perimeter = float(cv2.arcLength(contour, True))
            if perimeter > 0.0:
                circularity = (4.0 * math.pi * area) / (perimeter * perimeter)
            else:
                circularity = 0.0

            # Filter: noisy/degenerate region (very low circularity)
            if circularity < settings.REGION_MIN_CIRCULARITY:
                logger.debug(
                    "Region label=%d rejected: circularity=%.4f < min=%.4f",
                    label, circularity, settings.REGION_MIN_CIRCULARITY,
                )
                continue

            # ── Centroid (image moments) ──────────────────────────────────────
            M = cv2.moments(contour)
            if M["m00"] != 0.0:
                cx = M["m10"] / M["m00"]
                cy = M["m01"] / M["m00"]
            else:
                # Fallback: bounding box centre
                cx = x + w / 2.0
                cy = y + h / 2.0
            centroid = (round(cx, 2), round(cy, 2))

            # ── Mean VARI inside the blob ─────────────────────────────────────
            region_pixels = vari_map[blob_mask == 255]
            mean_vari = float(np.mean(region_pixels)) if region_pixels.size > 0 else 0.0

            # ── Build Region ──────────────────────────────────────────────────
            region = Region(
                temporary_region_id=str(uuid.uuid4()),
                frame_uuid=sf.frame_uuid,
                timestamp=sf.timestamp,
                centroid=centroid,
                bounding_box=bounding_box,
                contour=contour,
                pixel_count=pixel_count,
                area=round(area, 4),
                circularity=round(min(circularity, 1.0), 6),
                mean_vari=round(mean_vari, 6),
            )
            regions.append(region)

        logger.debug(
            "RegionExtractor: frame=%s blobs=%d accepted=%d",
            sf.frame_uuid[:8], num_labels - 1, len(regions),
        )
        return regions


# ── Helpers ────────────────────────────────────────────────────────────────────

def _touches_border(
    x: int, y: int, w: int, h: int,
    frame_w: int, frame_h: int,
    margin: int,
) -> bool:
    """Return True if the bounding box is within *margin* pixels of any edge."""
    return (
        x < margin
        or y < margin
        or (x + w) > (frame_w - margin)
        or (y + h) > (frame_h - margin)
    )
