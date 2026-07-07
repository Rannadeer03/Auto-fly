"""TrackedRegion — a vegetation region tracked across multiple frames.

A TrackedRegion wraps a sequence of per-frame Region objects that the
TrackingManager has determined to belong to the same physical vegetation
blob across consecutive video frames.

Ownership model
---------------
TrackedRegion instances are created and owned exclusively by TrackingManager.
Callers of TrackingManager.update() receive references into the manager's
live list — they must not mutate any field directly.  Fields are updated
only by TrackingManager between frames.

Field inventory
---------------
track_id          UUID4 string, assigned once at creation, permanent for the
                  lifetime of the track (and useful as a stable key for
                  downstream consumers — unlike Region.temporary_region_id).

state             Current TrackState (NEW / ACTIVE / LOST / FINISHED).

current_region    The Region matched in the most recent frame, or None when
                  the track is LOST (no match this frame).

track_age         Total number of frames since the track was first created,
                  including frames where no match was found.

frames_visible    Total number of frames where the track was successfully
                  matched to a Region.  frames_visible ≤ track_age always.

frames_missing    Number of *consecutive* frames since the last successful
                  match.  Reset to 0 on every successful match.  When this
                  exceeds TRACKING_MAX_FRAMES_MISSING the track becomes FINISHED.

best_region       The Region snapshot with the highest mean_vari ever seen
                  for this track.  Used as a quality proxy for the most
                  vegetation-dense observation.  Never None (always the first
                  region seen at minimum).

history           Ordered list of all matched Region snapshots, newest last.
                  Capped at TRACKING_MAX_HISTORY_LEN entries (FIFO eviction).
                  Empty only if the track was never matched (should not occur
                  in normal operation).

created_at        Monotonic timestamp (time.monotonic()) at first creation.
last_seen_at      Monotonic timestamp of the most recent successful match.
                  Equals created_at if the track has never been re-matched.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from vegetation.best_observation import BestObservation
from vegetation.region_model import Region
from vegetation.track_state import TrackState


@dataclass
class TrackedRegion:
    """A vegetation blob tracked across multiple frames.

    Created and mutated exclusively by TrackingManager.  External callers
    should treat instances as read-only snapshots.

    Do NOT add GPS, mission references, anomaly IDs, or database keys here.
    """

    # Stable identity
    track_id: str                        # UUID4 — permanent for this track's life

    # Lifecycle
    state: TrackState

    # Most-recent observation (None when LOST)
    current_region: Optional[Region]

    # Counters
    track_age: int                       # total frames since creation
    frames_visible: int                  # frames successfully matched
    frames_missing: int                  # consecutive unmatched frames (reset on match)

    # Quality — best Region ever seen for this track (highest mean_vari)
    best_region: Region                  # never None

    # Full ordered observation history (newest last, capped at TRACKING_MAX_HISTORY_LEN)
    history: List[Region] = field(default_factory=list)

    # Timing
    created_at: float = 0.0             # time.monotonic() at creation
    last_seen_at: float = 0.0           # time.monotonic() of last successful match

    # Best Observation (Phase 3E) — the single best-quality observation snapshot.
    # Set on first match, updated whenever a better observation is found
    # (smaller distance_from_image_center, with tiebreakers applied).
    # Frozen (never updated again) when state transitions to FINISHED.
    best_observation: Optional[BestObservation] = field(default=None)
    # Guard flag — set to True by TrackingManager when state → FINISHED.
    # After this, best_observation must never be replaced.
    best_observation_frozen: bool = False
