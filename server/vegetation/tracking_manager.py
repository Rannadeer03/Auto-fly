"""TrackingManager — associates vegetation regions across consecutive frames.

Overview
--------
TrackingManager is the sole Phase 3D component.  It consumes the
``List[Region]`` produced by ``VegetationPipeline.process_frame()`` and
maintains a pool of ``TrackedRegion`` objects whose IDs persist across frames.

Usage pattern::

    pipeline = VegetationPipeline()
    tracker  = TrackingManager()

    ctx = pipeline.start_session()
    tracker.reset()                          # sync lifetime with session

    # per-frame loop:
    sf = synchronizer.poll()
    if sf:
        regions       = pipeline.process_frame(sf)
        tracked       = tracker.update(regions, sf.frame_uuid, sf.timestamp)
        # `tracked` is List[TrackedRegion] — NEW + ACTIVE + LOST

    pipeline.end_session()
    tracker.reset()

Association algorithm
---------------------
For each call to ``update()``:

    1.  Compute a (n_active_tracks × n_incoming_regions) score matrix using
        the method selected by ``TRACKING_SIMILARITY_METHOD``.

    2.  Filter matrix entries that do not pass the corresponding threshold(s).

    3.  Greedy best-first assignment:
            - Flatten valid entries, sort by score descending.
            - Iterate: if both the track and region are still unassigned,
              create a (track_idx, region_idx) match.
        This is O(T·R·log(T·R)) — optimal for T, R < 100, which covers all
        realistic single-frame vegetation patch counts from an aerial camera.

    4.  Update matched tracks: state → ACTIVE, increment counters.
    5.  Update unmatched tracks: state → LOST; if frames_missing exceeds
        ``TRACKING_MAX_FRAMES_MISSING`` → state → FINISHED.
    6.  Create new tracks for unmatched regions: state → NEW.
    7.  Prune FINISHED tracks from the internal pool.
    8.  Return all surviving (NEW + ACTIVE + LOST) tracks.

Similarity methods
------------------
"centroid"
    Score = 1 − (centroid_dist / MAX_CENTROID_DIST_PX).
    Valid when centroid_dist ≤ MAX_CENTROID_DIST_PX.

"iou"
    Score = IoU(bb_track, bb_region).
    Valid when IoU ≥ TRACKING_MIN_IOU.

"area"
    Score = min(area_track, area_region) / max(area_track, area_region).
    Valid when area_similarity ≥ TRACKING_MIN_AREA_SIMILARITY.

"combined"
    Score = arithmetic mean of all three normalised scores.
    Valid only when ALL three individual constraints pass.

All thresholds are read from ``settings`` at call time — no magic numbers.

LOST-track reference position
------------------------------
When a track is LOST (current_region is None), the most recent entry in
``history`` is used as the reference position for the next frame's similarity
calculation.  This allows a vegetation blob that briefly disappears (e.g.
occluded by a drone shadow) to re-associate rather than spawning a new track.

Thread safety
-------------
TrackingManager is NOT thread-safe.  Call ``update()`` from a single thread.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from typing import List, Optional, Tuple

from config import settings
from vegetation.best_observation import BestObservation
from vegetation.mission_session_context import MissionSessionContext
from vegetation.region_model import Region
from vegetation.synchronized_frame import SynchronizedFrame
from vegetation.track_state import TrackState
from vegetation.tracked_region import TrackedRegion

logger = logging.getLogger(__name__)

# Type alias for internal match tuples (track_list_index, region_list_index)
_Match = Tuple[int, int]


class TrackingManager:
    """Associates vegetation regions across frames to produce stable track IDs.

    Instantiate once per session (or once globally and call reset() per session).
    """

    def __init__(self) -> None:
        # Pool of all live tracks (NEW + ACTIVE + LOST).
        # FINISHED tracks are removed before every return from update().
        self._tracks: List[TrackedRegion] = []

    # ── Public API ─────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Discard all tracks.  Call at the start / end of each mission session."""
        count = len(self._tracks)
        self._tracks = []
        logger.info("TrackingManager reset: cleared %d track(s)", count)

    def update(
        self,
        regions: List[Region],
        sf: SynchronizedFrame,
        session_ctx: Optional[MissionSessionContext] = None,
    ) -> List[TrackedRegion]:
        """Process one frame's regions and update the track pool.

        Parameters
        ----------
        regions:
            ``List[Region]`` from ``VegetationPipeline.process_frame()``.
            May be empty (no vegetation detected this frame).
        sf:
            The SynchronizedFrame. Used to assign telemetry to BestObservation.
        session_ctx:
            Optional MissionSessionContext.  When supplied, camera intrinsics
            (resolution, fov, mount_angle) are embedded in each BestObservation
            and completed tracks are recorded via
            ``session_ctx.add_completed_track()``.  May be None in tests.

        Returns
        -------
        List[TrackedRegion]
            All non-FINISHED tracks after the update — includes NEW, ACTIVE,
            and LOST states.  FINISHED tracks are removed and not returned.
        """
        # Only match against tracks that haven't been finalized
        live_tracks = [
            t for t in self._tracks
            if t.state in (TrackState.NEW, TrackState.ACTIVE, TrackState.LOST)
        ]

        # ── Step 1: Compute matches ────────────────────────────────────────────
        matches, unmatched_track_idxs, unmatched_region_idxs = self._match(
            live_tracks, regions
        )

        # ── Step 2: Update matched tracks ─────────────────────────────────────
        for track_idx, region_idx in matches:
            track = live_tracks[track_idx]
            region = regions[region_idx]
            self._apply_match(track, region, sf, session_ctx)

        # ── Step 3: Penalise unmatched tracks ─────────────────────────────────
        for track_idx in unmatched_track_idxs:
            track = live_tracks[track_idx]
            self._apply_miss(track, session_ctx)

        # ── Step 4: Create new tracks for unmatched regions ───────────────────
        for region_idx in unmatched_region_idxs:
            region = regions[region_idx]
            first_obs = self._build_observation(region, sf, session_ctx)
            new_track = TrackedRegion(
                track_id=str(uuid.uuid4()),
                state=TrackState.NEW,
                current_region=region,
                track_age=1,
                frames_visible=1,
                frames_missing=0,
                best_region=region,
                history=[region],
                created_at=sf.timestamp,
                last_seen_at=sf.timestamp,
                best_observation=first_obs,
                best_observation_frozen=False,
            )
            self._tracks.append(new_track)
            logger.debug(
                "TrackingManager: NEW track %s (centroid=%s  area=%.0f  vari=%.4f)",
                new_track.track_id[:8],
                region.centroid,
                region.area,
                region.mean_vari,
            )

        # ── Step 5: Prune FINISHED tracks from the pool ───────────────────────
        before = len(self._tracks)
        self._tracks = [t for t in self._tracks if t.state != TrackState.FINISHED]
        pruned = before - len(self._tracks)
        if pruned:
            logger.debug(
                "TrackingManager: pruned %d FINISHED track(s) (frame=%s)",
                pruned, sf.frame_uuid[:8],
            )

        logger.debug(
            "TrackingManager update: frame=%s  regions=%d  matches=%d  "
            "new=%d  lost_now=%d  total_live=%d",
            sf.frame_uuid[:8],
            len(regions),
            len(matches),
            len(unmatched_region_idxs),
            len(unmatched_track_idxs),
            len(self._tracks),
        )

        # Return a snapshot of the live pool (NEW + ACTIVE + LOST)
        return list(self._tracks)

    @property
    def active_track_count(self) -> int:
        """Number of non-FINISHED tracks currently in the pool."""
        return len(self._tracks)

    # ── Matching ───────────────────────────────────────────────────────────────

    def _match(
        self,
        tracks: List[TrackedRegion],
        regions: List[Region],
    ) -> Tuple[List[_Match], List[int], List[int]]:
        """Greedy best-first assignment between *tracks* and *regions*.

        Returns
        -------
        matches : List[Tuple[track_idx, region_idx]]
        unmatched_track_idxs : List[int]
        unmatched_region_idxs : List[int]
        """
        if not tracks:
            return [], [], list(range(len(regions)))
        if not regions:
            return [], list(range(len(tracks))), []

        # Build all valid (score, track_idx, region_idx) triples
        candidates: List[Tuple[float, int, int]] = []
        for ti, track in enumerate(tracks):
            ref = self._reference_region(track)
            if ref is None:
                continue
            for ri, region in enumerate(regions):
                score, valid = _similarity(ref, region)
                if valid:
                    candidates.append((score, ti, ri))

        # Sort by score descending — best match first
        candidates.sort(key=lambda x: x[0], reverse=True)

        matched_tracks: set[int] = set()
        matched_regions: set[int] = set()
        matches: List[_Match] = []

        for score, ti, ri in candidates:
            if ti not in matched_tracks and ri not in matched_regions:
                matches.append((ti, ri))
                matched_tracks.add(ti)
                matched_regions.add(ri)

        unmatched_tracks = [i for i in range(len(tracks)) if i not in matched_tracks]
        unmatched_regions = [i for i in range(len(regions)) if i not in matched_regions]

        return matches, unmatched_tracks, unmatched_regions

    @staticmethod
    def _reference_region(track: TrackedRegion) -> Optional[Region]:
        """Return the position reference for matching: current if ACTIVE,
        or last history entry when LOST (current_region is None)."""
        if track.current_region is not None:
            return track.current_region
        if track.history:
            return track.history[-1]
        return None

    # ── Track update helpers ───────────────────────────────────────────────────

    @staticmethod
    def _apply_match(
        track: TrackedRegion,
        region: Region,
        sf: SynchronizedFrame,
        session_ctx: Optional[MissionSessionContext] = None,
    ) -> None:
        """Update *track* after it has been matched to *region*."""
        track.current_region = region
        track.state = TrackState.ACTIVE
        track.track_age += 1
        track.frames_visible += 1
        track.frames_missing = 0
        track.last_seen_at = sf.timestamp

        # Update best-quality snapshot (Phase 3D: highest mean_vari)
        if region.mean_vari > track.best_region.mean_vari:
            track.best_region = region

        # Append to history (FIFO ring)
        track.history.append(region)
        if len(track.history) > settings.TRACKING_MAX_HISTORY_LEN:
            track.history.pop(0)

        # Update BestObservation (Phase 3E: smallest distance-to-center)
        if not track.best_observation_frozen:
            candidate = TrackingManager._build_observation(region, sf, session_ctx)
            if candidate is not None:
                if track.best_observation is None or _is_better_observation(
                    candidate, track.best_observation
                ):
                    track.best_observation = candidate

    @staticmethod
    def _apply_miss(
        track: TrackedRegion,
        session_ctx: Optional[MissionSessionContext] = None,
    ) -> None:
        """Update *track* when no region could be matched to it this frame."""
        track.track_age += 1
        track.frames_missing += 1
        track.current_region = None

        if track.frames_missing > settings.TRACKING_MAX_FRAMES_MISSING:
            track.state = TrackState.FINISHED
            # Phase 3E: freeze best_observation on finalization
            track.best_observation_frozen = True
            logger.debug(
                "TrackingManager: track %s → FINISHED (missing for %d frames)  "
                "best_obs_dist=%.1f",
                track.track_id[:8],
                track.frames_missing,
                track.best_observation.distance_from_image_center
                if track.best_observation else float("nan"),
            )
            # Record completed track in session context if provided
            if session_ctx is not None:
                session_ctx.add_completed_track(track)
        else:
            track.state = TrackState.LOST
            logger.debug(
                "TrackingManager: track %s → LOST (missing=%d / max=%d)",
                track.track_id[:8],
                track.frames_missing,
                settings.TRACKING_MAX_FRAMES_MISSING,
            )

    @staticmethod
    def _build_observation(
        region: Region,
        sf: SynchronizedFrame,
        session_ctx: Optional[MissionSessionContext] = None,
    ) -> Optional[BestObservation]:
        """Build a BestObservation from *region* + session camera metadata.

        Computes distance_from_image_center using the camera resolution from
        *session_ctx* if available, or falling back to settings.
        Returns None only if the region has no frame metadata.
        """
        from config import settings as _s  # avoid top-level circular import

        if session_ctx is not None:
            w, h = session_ctx.camera_resolution
            cam_fov = session_ctx.camera_fov
            cam_mount = session_ctx.camera_mount_angle
        else:
            w, h = _s.CAMERA_WIDTH, _s.CAMERA_HEIGHT
            cam_fov = (_s.CAMERA_HFOV_DEG, _s.CAMERA_VFOV_DEG)
            cam_mount = _s.CAMERA_PITCH_DEG

        img_cx = w / 2.0
        img_cy = h / 2.0
        cx, cy = region.centroid
        dist = math.sqrt((cx - img_cx) ** 2 + (cy - img_cy) ** 2)

        return BestObservation(
            frame_uuid=region.frame_uuid,
            timestamp=region.timestamp,
            latitude=sf.lat,
            longitude=sf.lon,
            altitude=sf.alt,
            heading=sf.heading,
            yaw=sf.yaw,
            ground_speed=sf.ground_speed,
            mission_progress=sf.mission_progress,
            waypoint_index=sf.waypoint,
            centroid=region.centroid,
            bounding_box=region.bounding_box,
            distance_from_image_center=round(dist, 4),
            mean_vari=region.mean_vari,
            camera_resolution=(w, h),
            camera_fov=cam_fov,
            camera_mount_angle=cam_mount,
        )



# ── Similarity functions (module-level, stateless) ─────────────────────────────

def _is_better_observation(
    candidate: "BestObservation",
    current: "BestObservation",
) -> bool:
    """Return True if *candidate* should replace *current* as the BestObservation.

    Selection rule (Phase 3E specification):
        Primary   — smallest distance_from_image_center.
        Tiebreaker (|d1 - d2| < OBS_CENTER_TIE_DIST_PX):
            1. Higher mean_vari
            2. Larger visible area (bounding_box area)
            3. Earlier timestamp
    """
    delta = candidate.distance_from_image_center - current.distance_from_image_center
    tie_band = settings.OBS_CENTER_TIE_DIST_PX

    # Candidate is clearly closer — always prefer it
    if delta < -tie_band:
        return True

    # Candidate is clearly farther — keep current
    if delta > tie_band:
        return False

    # Within the tie band — apply tiebreakers
    # 1. Higher mean_vari
    if candidate.mean_vari > current.mean_vari:
        return True
    if candidate.mean_vari < current.mean_vari:
        return False

    # 2. Larger bounding-box area
    cx, cy, cw, ch = candidate.bounding_box
    ox, oy, ow, oh = current.bounding_box
    cand_area = cw * ch
    curr_area = ow * oh
    if cand_area > curr_area:
        return True
    if cand_area < curr_area:
        return False

    # 3. Earlier timestamp (prefer the first occurrence on remaining ties)
    return candidate.timestamp < current.timestamp

def _similarity(ref: Region, candidate: Region) -> Tuple[float, bool]:
    """Compute a similarity score between *ref* (track reference) and *candidate*.

    Returns
    -------
    score : float  in [0, 1] — higher is more similar
    valid : bool   — True when the score meets the configured threshold
    """
    method = settings.TRACKING_SIMILARITY_METHOD

    if method == "centroid":
        return _centroid_similarity(ref, candidate)

    if method == "iou":
        return _iou_similarity(ref, candidate)

    if method == "area":
        return _area_similarity(ref, candidate)

    if method == "combined":
        return _combined_similarity(ref, candidate)

    # Unknown method — fall back to centroid with a warning logged once
    logger.warning(
        "Unknown TRACKING_SIMILARITY_METHOD=%r; falling back to 'centroid'",
        method,
    )
    return _centroid_similarity(ref, candidate)


def _centroid_similarity(ref: Region, candidate: Region) -> Tuple[float, bool]:
    """Score based on Euclidean centroid distance."""
    dx = ref.centroid[0] - candidate.centroid[0]
    dy = ref.centroid[1] - candidate.centroid[1]
    dist = math.sqrt(dx * dx + dy * dy)
    max_dist = settings.TRACKING_MAX_CENTROID_DIST_PX
    if max_dist <= 0.0:
        return 0.0, False
    score = max(0.0, 1.0 - dist / max_dist)
    return score, dist <= max_dist


def _iou_similarity(ref: Region, candidate: Region) -> Tuple[float, bool]:
    """Score based on bounding-box IoU."""
    iou = _compute_iou(ref.bounding_box, candidate.bounding_box)
    return iou, iou >= settings.TRACKING_MIN_IOU


def _area_similarity(ref: Region, candidate: Region) -> Tuple[float, bool]:
    """Score based on contour area ratio."""
    sim = _compute_area_similarity(ref.area, candidate.area)
    return sim, sim >= settings.TRACKING_MIN_AREA_SIMILARITY


def _combined_similarity(ref: Region, candidate: Region) -> Tuple[float, bool]:
    """Score = mean(centroid_score, iou_score, area_score).
    Valid only when ALL three individual constraints pass."""
    c_score, c_valid = _centroid_similarity(ref, candidate)
    i_score, i_valid = _iou_similarity(ref, candidate)
    a_score, a_valid = _area_similarity(ref, candidate)
    valid = c_valid and i_valid and a_valid
    score = (c_score + i_score + a_score) / 3.0
    return score, valid


# ── Geometry helpers ───────────────────────────────────────────────────────────

def _compute_iou(
    bb1: Tuple[int, int, int, int],
    bb2: Tuple[int, int, int, int],
) -> float:
    """Intersection-over-Union of two axis-aligned bounding boxes (x,y,w,h)."""
    x1, y1, w1, h1 = bb1
    x2, y2, w2, h2 = bb2

    # Intersection rectangle
    inter_x1 = max(x1, x2)
    inter_y1 = max(y1, y2)
    inter_x2 = min(x1 + w1, x2 + w2)
    inter_y2 = min(y1 + h1, y2 + h2)

    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    intersection = float(inter_w * inter_h)

    area1 = float(w1 * h1)
    area2 = float(w2 * h2)
    union = area1 + area2 - intersection

    if union <= 0.0:
        return 0.0
    return intersection / union


def _compute_area_similarity(area1: float, area2: float) -> float:
    """min(a1, a2) / max(a1, a2) ∈ [0, 1] — 1.0 for equal areas."""
    if area1 <= 0.0 and area2 <= 0.0:
        return 1.0
    max_area = max(area1, area2)
    if max_area == 0.0:
        return 0.0
    return min(area1, area2) / max_area
