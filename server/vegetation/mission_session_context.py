"""MissionSessionContext — per-session camera and mission metadata.

Captures the static configuration that applies to an entire mission session
(camera intrinsics, mounting geometry).  This context is created once when a
session starts and does not change during the session.

Phase 3E addition: MissionSessionContext also accumulates completed tracks
(TrackedRegion objects that have transitioned to FINISHED) via
``add_completed_track()``.  Each completed track is summarised into a
``CompletedTrack`` value object that stores only the fields needed for
post-flight analysis — no live mutable state is retained.

Fields (MissionSessionContext)
------------------------------
session_id         UUID4 string uniquely identifying this analysis session.
started_at         Monotonic timestamp (time.monotonic()) at session start.
camera_resolution  (width, height) in pixels from settings.
camera_fps         Configured frames-per-second from settings.
camera_fov         (hfov_deg, vfov_deg) horizontal and vertical field of view
                   in degrees from settings.
camera_mount_angle Camera pitch in degrees from settings (e.g. −90.0 = nadir).
completed_tracks   Ordered list of CompletedTrack summaries appended as tracks
                   finish during the session.

Fields (CompletedTrack)
-----------------------
track_id           Permanent UUID4 from TrackedRegion.track_id.
best_observation   The frozen BestObservation (may be None if the track was
                   created and immediately lost without ever matching).
track_age          Total frames since track creation.
frames_visible     Frames successfully matched.
mean_vari_peak     mean_vari of the best_region (highest VARI seen).
history_length     Number of observations retained in the history ring.

Usage
-----
    ctx = MissionSessionContext.from_settings()
    # At the end of a session:
    for ct in ctx.completed_tracks:
        print(ct.track_id, ct.best_observation)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    # Imported only for type-checking; avoids a runtime circular import because
    # TrackedRegion imports BestObservation which imports nothing from here.
    from vegetation.tracked_region import TrackedRegion

from vegetation.best_observation import BestObservation
from vegetation.projection_result import ProjectionResult
from vegetation.camera_projection import project_observation
from vegetation.anomaly import Anomaly

@dataclass
class CompletedTrack:
    """Immutable summary of a FINISHED TrackedRegion.

    Created once by MissionSessionContext.add_completed_track() when a track
    finalizes.  Does not hold a live reference to the TrackedRegion.
    """

    track_id: str
    best_observation: Optional[BestObservation]   # frozen at finalization
    projection: Optional[ProjectionResult]        # camera projection (Phase 3E.5)
    track_age: int
    frames_visible: int
    history_length: int                           # len(history) at finalization
    
    # Phase 3F — Anomaly Inputs
    mean_vari: float                              # VARI from best_observation
    max_vari: float                               # Highest VARI seen in history
    average_vari: float                           # Average VARI across history
    pixel_area: float                             # Pixel area of best_observation

    def to_dict(self) -> dict:
        """JSON-serialisable summary."""
        obs = None
        if self.best_observation is not None:
            bo = self.best_observation
            obs = {
                "frame_uuid": bo.frame_uuid,
                "timestamp": bo.timestamp,
                "centroid": list(bo.centroid),
                "bounding_box": list(bo.bounding_box),
                "distance_from_image_center": bo.distance_from_image_center,
                "mean_vari": bo.mean_vari,
                "camera_resolution": list(bo.camera_resolution),
                "camera_fov": list(bo.camera_fov),
                "camera_mount_angle": bo.camera_mount_angle,
            }
        
        proj = None
        if self.projection is not None:
            pr = self.projection
            proj = {
                "latitude": pr.latitude,
                "longitude": pr.longitude,
                "ground_offset_x_m": pr.ground_offset_x_m,
                "ground_offset_y_m": pr.ground_offset_y_m,
                "ground_distance_m": pr.ground_distance_m,
                "bearing_deg": pr.bearing_deg,
                "estimated_error_m": pr.estimated_error_m,
                "projection_timestamp": pr.projection_timestamp,
            }
            
        return {
            "track_id": self.track_id,
            "best_observation": obs,
            "projection": proj,
            "track_age": self.track_age,
            "frames_visible": self.frames_visible,
            "history_length": self.history_length,
            "mean_vari": self.mean_vari,
            "max_vari": self.max_vari,
            "average_vari": self.average_vari,
            "pixel_area": self.pixel_area,
        }


@dataclass
class MissionSessionContext:
    """Static per-session metadata snapshot + completed track accumulator.

    Created once at session start via `from_settings()`.
    The camera geometry fields are immutable; completed_tracks grows as
    tracks finalize during the session.
    """

    session_id: str
    started_at: float                          # time.monotonic()

    # Camera geometry (from settings at session-start time)
    camera_resolution: tuple[int, int]         # (width_px, height_px)
    camera_fps: int
    camera_fov: tuple[float, float]            # (hfov_deg, vfov_deg)
    camera_mount_angle: float                  # CAMERA_PITCH_DEG (degrees)

    # Completed track accumulator (Phase 3E)
    completed_tracks: List[CompletedTrack] = field(default_factory=list)
    
    # Anomaly accumulator (Phase 3F)
    completed_anomalies: List[Anomaly] = field(default_factory=list)

    # ── Factory ────────────────────────────────────────────────────────────────

    @classmethod
    def from_settings(cls) -> "MissionSessionContext":
        """Create a context snapshot from the current application settings."""
        # Import here to avoid a circular-import at module load time
        from config import settings  # noqa: PLC0415

        return cls(
            session_id=str(uuid.uuid4()),
            started_at=time.monotonic(),
            camera_resolution=(settings.CAMERA_WIDTH, settings.CAMERA_HEIGHT),
            camera_fps=settings.CAMERA_FPS,
            camera_fov=(settings.CAMERA_HFOV_DEG, settings.CAMERA_VFOV_DEG),
            camera_mount_angle=settings.CAMERA_PITCH_DEG,
        )

    # ── Track finalization ─────────────────────────────────────────────────────

    def add_completed_track(self, track: "TrackedRegion") -> None:
        """Record a FINISHED track as a CompletedTrack summary.

        Called by TrackingManager._apply_miss() immediately after
        track.state is set to FINISHED.  Safe to call multiple times with
        the same track_id (duplicate guard included).
        """
        # Duplicate guard — should not happen, but be defensive
        existing_ids = {ct.track_id for ct in self.completed_tracks}
        if track.track_id in existing_ids:
            return
            
        proj = None
        mean_vari = 0.0
        max_vari = 0.0
        avg_vari = 0.0
        pixel_area = 0.0
        
        if track.best_observation is not None:
            proj = project_observation(track.best_observation)
            mean_vari = track.best_observation.mean_vari
            cw, ch = track.best_observation.bounding_box[2:]
            pixel_area = float(cw * ch)
            
        if track.history:
            varis = [r.mean_vari for r in track.history]
            max_vari = max(varis)
            avg_vari = sum(varis) / len(varis)
        elif track.best_observation is not None:
            max_vari = mean_vari
            avg_vari = mean_vari

        ct = CompletedTrack(
            track_id=track.track_id,
            best_observation=track.best_observation,  # already frozen
            projection=proj,
            track_age=track.track_age,
            frames_visible=track.frames_visible,
            history_length=len(track.history),
            mean_vari=mean_vari,
            max_vari=max_vari,
            average_vari=avg_vari,
            pixel_area=pixel_area,
        )
        self.completed_tracks.append(ct)
        
        from vegetation.anomaly_builder import AnomalyBuilder
        anomaly = AnomalyBuilder.build(ct)
        if anomaly is not None:
            self.completed_anomalies.append(anomaly)

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Return a JSON-serialisable representation for logging / storage."""
        # Anomalies are domain objects; they can be serialised elsewhere
        # if needed, but we keep MissionSessionContext output simple for now.
        return {
            "session_id": self.session_id,
            "started_at": self.started_at,
            "camera_resolution": list(self.camera_resolution),
            "camera_fps": self.camera_fps,
            "camera_fov": list(self.camera_fov),
            "camera_mount_angle": self.camera_mount_angle,
            "completed_tracks_count": len(self.completed_tracks),
            "completed_anomalies_count": len(self.completed_anomalies),
        }
