"""BestObservation — the single best-quality observation snapshot for a track.

Selection rule (Phase 3E specification)
---------------------------------------
For each region successfully matched to a track, compute the Euclidean
distance from the region's centroid to the image centre:

    dist = sqrt((cx - W/2)² + (cy - H/2)²)

The candidate with the **smallest** distance_from_image_center is preferred.
This ensures the observation captured when the vegetation patch was most
centred in the camera frame — giving the least perspective distortion and the
most reliable geometry.

Tiebreaker (when |d1 - d2| < OBS_CENTER_TIE_DIST_PX)
------------------------------------------------------
1. Higher mean_vari   — more vigorous vegetation response.
2. Larger visible area — more pixels → richer measurement.
3. Earlier timestamp  — first occurrence wins on remaining ties.

Do NOT use:
- Highest VARI (explicitly excluded by spec)
- First frame (explicitly excluded by spec)
- Last frame  (explicitly excluded by spec)

Field inventory (exact Phase 3E specification)
----------------------------------------------
frame_uuid             UUID from the SynchronizedFrame that produced this
                       observation.
timestamp              Monotonic timestamp from the SynchronizedFrame.
latitude               Drone latitude in decimal degrees at capture time.
longitude              Drone longitude in decimal degrees at capture time.
altitude               Drone altitude in metres (relative) at capture time.
heading                Compass heading (°) at capture time.
yaw                    Yaw angle (°) at capture time.
ground_speed           Ground speed (m/s) at capture time.
mission_progress       Fraction [0.0, 1.0] of mission completed.
waypoint_index         Current waypoint sequence number.
centroid               (cx, cy) centroid of the region in pixel space.
bounding_box           (x, y, w, h) axis-aligned bounding rectangle (pixels).
distance_from_image_center
                       Euclidean distance (pixels) from centroid to the image
                       frame centre.  The primary selection criterion.
mean_vari              Mean VARI value inside the region mask.
camera_resolution      (width, height) in pixels from MissionSessionContext.
camera_fov             (hfov_deg, vfov_deg) from MissionSessionContext.
camera_mount_angle     Camera pitch (degrees) from MissionSessionContext.

Downstream notes
----------------
This dataclass intentionally does NOT include GPS polygon projections — that
is Phase 3F work.  GPS coordinates (lat, lon, alt) here are the *drone*
position at capture time, not the projected ground coordinates of the patch.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BestObservation:
    """The single best-quality observation snapshot for one TrackedRegion.

    Created and updated exclusively by TrackingManager.
    Frozen (no further updates) when the track becomes FINISHED.

    Do NOT add GPS projection, anomaly scoring, or mission waypoints here.
    """

    # Frame identity
    frame_uuid: str                          # UUID from the SynchronizedFrame
    timestamp: float                         # Monotonic timestamp

    # Drone telemetry at capture time
    latitude: float
    longitude: float
    altitude: float
    heading: float
    yaw: float
    ground_speed: float
    mission_progress: float
    waypoint_index: int

    # Geometry (pixel space)
    centroid: tuple[float, float]            # (cx, cy)
    bounding_box: tuple[int, int, int, int]  # (x, y, w, h)
    distance_from_image_center: float        # pixels — primary selection key

    # Radiometric descriptor
    mean_vari: float

    # Camera intrinsics (snapshot from MissionSessionContext at session start)
    camera_resolution: tuple[int, int]       # (width_px, height_px)
    camera_fov: tuple[float, float]          # (hfov_deg, vfov_deg)
    camera_mount_angle: float                # degrees (e.g. -90.0 = nadir)
