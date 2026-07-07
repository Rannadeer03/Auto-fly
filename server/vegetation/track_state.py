"""TrackState — lifecycle states for a multi-frame vegetation track.

State machine
-------------

    NEW ──────────────────────────────────────────────────────────► FINISHED
     │   (never matched again before                                    ▲
     │    MAX_FRAMES_MISSING exceeded)                                  │
     │                                                                  │
     ▼ (matched again)                                                  │
    ACTIVE ──────────────────── (unmatched) ──────────► LOST ──────────┤
     ▲                                                   │  (MAX_FRAMES_MISSING
     └───────────────── (matched again) ─────────────────┘   exceeded)
                                                             → FINISHED

Transitions
-----------
NEW
    Created this frame — the track has never been matched more than once.
    Transitions to ACTIVE on the next successful match, or to LOST if
    missed immediately, following the same rules as any other state.

ACTIVE
    The track was matched in the most recent frame (frames_missing == 0).
    This is the normal healthy state.

LOST
    The track was NOT matched for one or more consecutive frames
    (1 ≤ frames_missing ≤ TRACKING_MAX_FRAMES_MISSING).
    The track is retained so a re-appearing region can be associated with
    it rather than creating a spurious new track.

FINISHED
    frames_missing exceeded TRACKING_MAX_FRAMES_MISSING.
    The track is removed from the active pool and will never be updated again.
    CalIers that cached a reference to a FINISHED TrackedRegion should
    treat it as read-only history.
"""

from __future__ import annotations

from enum import Enum


class TrackState(str, Enum):
    """Lifecycle state of a TrackedRegion.

    Inheriting from ``str`` allows JSON serialisation without a custom encoder
    (e.g. ``json.dumps({"state": TrackState.ACTIVE})`` produces ``"ACTIVE"``).
    """

    NEW = "NEW"
    ACTIVE = "ACTIVE"
    LOST = "LOST"
    FINISHED = "FINISHED"
