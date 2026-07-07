"""Region — the single output unit of the Phase 3C Region Extractor.

A Region represents one connected vegetation blob extracted from a single
processed camera frame.  It carries geometric descriptors computed entirely
in pixel space; no GPS, no anomaly IDs, no tracking state.

Field inventory (exactly the Phase 3C specification — nothing more):

    temporary_region_id  UUID4 string.  "Temporary" signals that this ID does
                         NOT persist across frames and MUST NOT be stored,
                         indexed, or used as a stable key.  It exists only so
                         that debug annotation and unit tests can refer to a
                         specific region within one frame.

    frame_uuid           UUID from the SynchronizedFrame that produced this
                         region.  Links the region back to its frame for
                         debug writers and future pipeline stages.

    timestamp            Monotonic timestamp (float) copied from the parent
                         SynchronizedFrame.  Same unit as time.monotonic().

    centroid             (cx, cy) tuple of float pixel coordinates — the
                         image moment centroid of the region's contour.

    bounding_box         (x, y, w, h) in pixels, axis-aligned rectangle from
                         cv2.boundingRect().

    contour              np.ndarray of shape (N, 1, 2), dtype int32 — the raw
                         OpenCV contour.  Stored for downstream use (GPS
                         polygon estimation, further shape analysis, debug
                         overlay).  Not serialised to JSON by default.

    pixel_count          Number of foreground pixels in the connected component
                         (from connectedComponentsWithStats CC_STAT_AREA).

    area                 cv2.contourArea(contour) — float, in square pixels.
                         Slightly different from pixel_count because contourArea
                         uses a polygon approximation, not a pixel count.

    circularity          4π × area / perimeter² ∈ [0, 1].  A perfect circle
                         yields 1.0; a long thin filament approaches 0.
                         Computed with perimeter = cv2.arcLength(contour, True).
                         Guarded against zero-perimeter contours (→ 0.0).

    mean_vari            Mean VARI value of all pixels inside this region's
                         mask, computed from the float32 VARI map passed to
                         RegionExtractor.  Provides a vegetation-health proxy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Region:
    """One connected vegetation blob extracted from a single camera frame.

    Do NOT add GPS, anomaly IDs, tracking fields, or mission references here.
    This dataclass is the canonical Phase 3C output; downstream phases will
    wrap or extend it rather than mutating it.
    """

    # Identity
    temporary_region_id: str       # UUID4 — ephemeral, per-frame only
    frame_uuid: str                # UUID from the parent SynchronizedFrame
    timestamp: float               # Monotonic timestamp from SynchronizedFrame

    # Geometry (pixel space)
    centroid: tuple[float, float]                    # (cx, cy)
    bounding_box: tuple[int, int, int, int]          # (x, y, w, h)
    contour: np.ndarray = field(repr=False)          # shape (N, 1, 2), int32

    # Shape descriptors
    pixel_count: int                                 # foreground pixels
    area: float                                      # cv2.contourArea result
    circularity: float                               # 4π·area / perimeter²

    # Radiometric descriptor
    mean_vari: float                                 # mean VARI inside the mask
