"""DebugWriter — developer-only annotated frame writer.

NEVER call this from any production API endpoint, streaming route, or mission
runner.  It is activated exclusively when DEBUG_VARI=true in the environment.

What it writes
--------------
For each processed frame it saves a JPEG to DEBUG_VARI_DIR named:
    frame_<frame_uuid>.jpg

The JPEG is a copy of the original BGR camera frame annotated with:
    - Green filled contour overlay (VARI vegetation mask)
    - Green bounding box rectangle
    - Cyan dot at the centroid
    - White region number label (index in the list, 0-based) at the centroid

Output directory
----------------
DEBUG_VARI_DIR is created on first write if it does not exist.  Files
accumulate across runs (no automatic cleanup) — the developer is responsible
for purging the directory when the disk fills up.

Thread safety
-------------
Not thread-safe.  Call from the same thread as VegetationPipeline.process_frame.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from config import settings
from vegetation.region_model import Region
from vegetation.synchronized_frame import SynchronizedFrame
from vegetation.tracked_region import TrackedRegion

logger = logging.getLogger(__name__)

# Annotation colour constants (BGR)
_COLOUR_CONTOUR = (0, 200, 0)           # Green — region contour
_COLOUR_BBOX = (0, 200, 0)              # Green — bounding box
_COLOUR_CENTROID = (255, 255, 0)        # Cyan  — centroid dot
_COLOUR_LABEL = (255, 255, 255)         # White — region number label

# Phase 3E — tracking overlay colours
_COLOUR_TRACK_ID = (180, 255, 180)      # Light green — track ID text
_COLOUR_DIST_LABEL = (200, 200, 50)     # Steel blue  — distance label
_COLOUR_BEST_MARKER = (0, 215, 255)     # Gold  — best observation star
_COLOUR_CENTER_CROSS = (100, 100, 255)  # Red   — image center crosshair

_FONT = cv2.FONT_HERSHEY_SIMPLEX
_FONT_SCALE = 0.5
_FONT_THICKNESS = 1
_LINE_THICKNESS = 1
_CENTROID_RADIUS = 4


class DebugWriter:
    """Writes annotated debug frames to disk.

    Instantiate once and reuse.  The DEBUG_VARI_DIR is created on the first
    write if it doesn't exist.
    """

    def __init__(self) -> None:
        self._dir_created: bool = False

    def write(
        self,
        sf: SynchronizedFrame,
        vari_map: Optional[np.ndarray],
        regions: List[Region],
    ) -> None:
        """Write an annotated debug frame to DEBUG_VARI_DIR.

        Parameters
        ----------
        sf:
            The SynchronizedFrame whose image is annotated.
        vari_map:
            float32 VARI map (H, W) — currently unused in annotation but
            passed for future visualisation (e.g. false-colour overlay).
        regions:
            List of Region objects extracted from this frame.
        """
        if not settings.DEBUG_VARI:
            return

        self._ensure_dir()

        # Work on a copy so we never mutate the original frame
        canvas = sf.image.copy()

        for idx, region in enumerate(regions):
            # ── Contour overlay ────────────────────────────────────────────────
            cv2.drawContours(
                canvas, [region.contour], -1, _COLOUR_CONTOUR, _LINE_THICKNESS
            )

            # ── Bounding box ───────────────────────────────────────────────────
            x, y, w, h = region.bounding_box
            cv2.rectangle(canvas, (x, y), (x + w, y + h), _COLOUR_BBOX, _LINE_THICKNESS)

            # ── Centroid ───────────────────────────────────────────────────────
            cx = int(round(region.centroid[0]))
            cy = int(round(region.centroid[1]))
            cv2.circle(canvas, (cx, cy), _CENTROID_RADIUS, _COLOUR_CENTROID, -1)

            # ── Region number label ────────────────────────────────────────────
            label_text = str(idx)
            text_x = max(0, cx + _CENTROID_RADIUS + 2)
            text_y = max(_CENTROID_RADIUS, cy - _CENTROID_RADIUS)
            cv2.putText(
                canvas,
                label_text,
                (text_x, text_y),
                _FONT,
                _FONT_SCALE,
                _COLOUR_LABEL,
                _FONT_THICKNESS,
                cv2.LINE_AA,
            )

        # ── Frame metadata overlay ─────────────────────────────────────────────
        meta = (
            f"frame#{sf.frame_number}  uuid={sf.frame_uuid[:8]}  "
            f"regions={len(regions)}"
        )
        cv2.putText(
            canvas, meta, (4, 16), _FONT, 0.45, (0, 255, 255), 1, cv2.LINE_AA
        )

        # ── Write JPEG ─────────────────────────────────────────────────────────
        out_path = settings.DEBUG_VARI_DIR / f"frame_{sf.frame_uuid}.jpg"
        ok = cv2.imwrite(str(out_path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            logger.warning("DebugWriter: failed to write %s", out_path)
        else:
            logger.debug("DebugWriter: wrote %s (%d regions)", out_path.name, len(regions))

    # ── Private ────────────────────────────────────────────────────────────────

    def _ensure_dir(self) -> None:
        if not self._dir_created:
            try:
                settings.DEBUG_VARI_DIR.mkdir(parents=True, exist_ok=True)
                self._dir_created = True
            except OSError as exc:
                logger.error(
                    "DebugWriter: cannot create directory %s: %s",
                    settings.DEBUG_VARI_DIR, exc,
                )

    # ── Phase 3E — tracked frame writer ───────────────────────────────────────

    def write_tracked(
        self,
        sf: SynchronizedFrame,
        tracked: List[TrackedRegion],
    ) -> None:
        """Write a debug frame annotated with Phase 3E tracking information.

        Overlays (all gated by DEBUG_VARI=true):
            - Image-centre crosshair
            - Per-track: short track ID, distance-to-center label
            - Gold star on the centroid of the current BestObservation
            - Green contour / bounding box (from current_region)

        NEVER call from any production API endpoint.

        Parameters
        ----------
        sf:
            The SynchronizedFrame whose image is annotated.
        tracked:
            List[TrackedRegion] from TrackingManager.update().
        """
        if not settings.DEBUG_VARI:
            return

        self._ensure_dir()

        canvas = sf.image.copy()
        h, w = canvas.shape[:2]
        img_cx, img_cy = w // 2, h // 2

        # ── Image-centre crosshair ─────────────────────────────────────────────
        cross_arm = 20
        cv2.line(canvas,
                 (img_cx - cross_arm, img_cy),
                 (img_cx + cross_arm, img_cy),
                 _COLOUR_CENTER_CROSS, 1, cv2.LINE_AA)
        cv2.line(canvas,
                 (img_cx, img_cy - cross_arm),
                 (img_cx, img_cy + cross_arm),
                 _COLOUR_CENTER_CROSS, 1, cv2.LINE_AA)

        for track in tracked:
            region = track.current_region
            if region is None:
                continue  # LOST — no current position to draw

            # ── Contour + bounding box ─────────────────────────────────────────
            cv2.drawContours(canvas, [region.contour], -1, _COLOUR_CONTOUR, 1)
            x, y, bw, bh = region.bounding_box
            cv2.rectangle(canvas, (x, y), (x + bw, y + bh), _COLOUR_BBOX, 1)

            # ── Centroid dot ───────────────────────────────────────────────────
            cx = int(round(region.centroid[0]))
            cy = int(round(region.centroid[1]))
            cv2.circle(canvas, (cx, cy), _CENTROID_RADIUS, _COLOUR_CENTROID, -1)

            # ── Track ID label ─────────────────────────────────────────────────
            tid_text = track.track_id[:8]
            cv2.putText(
                canvas, tid_text,
                (max(0, cx + _CENTROID_RADIUS + 2), max(_CENTROID_RADIUS, cy - 10)),
                _FONT, 0.4, _COLOUR_TRACK_ID, 1, cv2.LINE_AA,
            )

            # ── Distance-to-center label ───────────────────────────────────────
            if track.best_observation is not None:
                dist_px = track.best_observation.distance_from_image_center
                dist_text = f"d={dist_px:.0f}px"
                cv2.putText(
                    canvas, dist_text,
                    (max(0, cx + _CENTROID_RADIUS + 2), max(_CENTROID_RADIUS, cy + 10)),
                    _FONT, 0.35, _COLOUR_DIST_LABEL, 1, cv2.LINE_AA,
                )

            # ── Best Observation marker (gold star / circle) ───────────────────
            # Mark the position that is currently recorded as the best
            if (track.best_observation is not None
                    and track.best_observation.frame_uuid == region.frame_uuid):
                # Current frame IS the best — draw a hollow gold circle
                cv2.circle(canvas, (cx, cy), _CENTROID_RADIUS + 5,
                           _COLOUR_BEST_MARKER, 2)

        # ── Frame metadata overlay ─────────────────────────────────────────────
        meta = (
            f"frame#{sf.frame_number}  uuid={sf.frame_uuid[:8]}  "
            f"tracks={len(tracked)}"
        )
        cv2.putText(
            canvas, meta, (4, 16), _FONT, 0.45, (0, 255, 255), 1, cv2.LINE_AA
        )

        out_path = settings.DEBUG_VARI_DIR / f"tracked_{sf.frame_uuid}.jpg"
        ok = cv2.imwrite(str(out_path), canvas, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            logger.warning("DebugWriter: failed to write tracked frame %s", out_path)
        else:
            logger.debug(
                "DebugWriter: wrote tracked frame %s (%d tracks)",
                out_path.name, len(tracked),
            )
