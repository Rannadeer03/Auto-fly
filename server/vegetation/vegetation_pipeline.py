"""VegetationPipeline — top-level assembler for the Phase 3 VARI pipeline.

Orchestrates all stages in order:

    SynchronizedFrame
        │
        ▼  VARIProcessor
        │     float32 VARI map
        ▼  ThresholdProcessor
        │     uint8 binary mask
        ▼  MorphologyProcessor
        │     cleaned uint8 mask
        ▼  RegionExtractor
        │     List[Region]
        ▼  DebugWriter  (no-op unless DEBUG_VARI=true)
        │
        ▼  returns List[Region]

Session lifecycle
-----------------
Call `start_session()` before the first frame — it creates a
MissionSessionContext and resets the FrameSynchronizer's counter.
Call `end_session()` when the mission finishes.

Calling `process_frame()` without starting a session works (the pipeline
runs without a context) but is not recommended for production use.

Usage
-----
    pipeline = VegetationPipeline()
    ctx = pipeline.start_session()

    # In the mission loop:
    sf = frame_synchronizer.poll()
    if sf:
        regions = pipeline.process_frame(sf)
        tracked = tracker.update(regions, sf, ctx)

    pipeline.end_session()

Thread safety
-------------
`process_frame()` is NOT thread-safe.  All calls must originate from the
same thread.  The underlying CameraService and DroneState are thread-safe;
only this pipeline's internal state is not.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from vegetation.debug_writer import DebugWriter
from vegetation.mission_session_context import MissionSessionContext
from vegetation.morphology_processor import MorphologyProcessor
from vegetation.region_extractor import RegionExtractor
from vegetation.region_model import Region
from vegetation.synchronized_frame import SynchronizedFrame
from vegetation.threshold_processor import ThresholdProcessor
from vegetation.vari_processor import VARIProcessor

logger = logging.getLogger(__name__)


class VegetationPipeline:
    """Full Phase 3 pipeline: SynchronizedFrame → List[Region].

    Instantiate once and reuse.  Each call to `process_frame` is independent;
    no state accumulates between calls.
    """

    def __init__(self) -> None:
        self._vari = VARIProcessor()
        self._threshold = ThresholdProcessor()
        self._morphology = MorphologyProcessor()
        self._extractor = RegionExtractor()
        self._debug = DebugWriter()

        self._session: Optional[MissionSessionContext] = None

    # ── Session lifecycle ──────────────────────────────────────────────────────

    def start_session(self) -> MissionSessionContext:
        """Begin a new analysis session.

        Creates and stores a MissionSessionContext from the current settings.
        Returns the context so the caller can log or store it.
        """
        self._session = MissionSessionContext.from_settings()
        logger.info(
            "VegetationPipeline session started: id=%s  resolution=%dx%d  "
            "fps=%d  fov=(%.1f°, %.1f°)  mount=%.1f°",
            self._session.session_id,
            *self._session.camera_resolution,
            self._session.camera_fps,
            *self._session.camera_fov,
            self._session.camera_mount_angle,
        )
        return self._session

    def end_session(self) -> None:
        """Mark the current session as ended."""
        if self._session is not None:
            logger.info(
                "VegetationPipeline session ended: id=%s", self._session.session_id
            )
        self._session = None

    @property
    def session_context(self) -> Optional[MissionSessionContext]:
        """The active MissionSessionContext, or None if no session is running."""
        return self._session

    # ── Frame processing ───────────────────────────────────────────────────────

    def process_frame(self, sf: SynchronizedFrame) -> List[Region]:
        """Run all pipeline stages on one SynchronizedFrame.

        Parameters
        ----------
        sf:
            A SynchronizedFrame produced by FrameSynchronizer.poll().

        Returns
        -------
        List[Region]
            Zero or more Region objects extracted from the frame after all
            filters are applied.  May be empty.

        Raises
        ------
        ValueError
            If the frame image is missing or malformed.  The caller should
            catch this and skip the frame rather than crashing the loop.
        """
        if sf.image is None or sf.image.size == 0:
            raise ValueError(f"SynchronizedFrame {sf.frame_uuid} has an empty image")

        # Stage 1 — VARI
        vari_map = self._vari.process(sf.image)

        # Stage 2 — Threshold
        binary_mask = self._threshold.process(vari_map)

        # Stage 3 — Morphology
        cleaned_mask = self._morphology.process(binary_mask)

        # Stage 4 — Region extraction (connected components → filtered regions)
        regions = self._extractor.extract(sf, cleaned_mask, vari_map)

        # Stage 5 — Debug annotation (no-op unless DEBUG_VARI=true)
        self._debug.write(sf, vari_map, regions)

        return regions
