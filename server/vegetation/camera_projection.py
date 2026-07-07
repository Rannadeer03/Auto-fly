"""Camera Projection pipeline.

Transforms a BestObservation into a ProjectionResult.
"""

import time
import math
from vegetation.best_observation import BestObservation
from vegetation.projection_result import ProjectionResult
from vegetation import projection_math

def project_observation(obs: BestObservation) -> ProjectionResult:
    """Project a BestObservation onto the ground plane.
    
    If the centroid is exactly at the image center, the ground offset is zero
    and the estimated GPS equals the drone GPS.
    """
    cx, cy = obs.centroid
    img_w, img_h = obs.camera_resolution
    
    px_x, px_y = projection_math.compute_pixel_offset(cx, cy, img_w, img_h)
    
    # Phase 3E.5 Rule: If centroid is exactly at image center, Ground offset = 0
    if abs(px_x) < 1e-3 and abs(px_y) < 1e-3:
        return ProjectionResult(
            latitude=obs.latitude,
            longitude=obs.longitude,
            ground_offset_x_m=0.0,
            ground_offset_y_m=0.0,
            ground_distance_m=0.0,
            bearing_deg=obs.heading,
            estimated_error_m=2.5,
            projection_timestamp=time.time()
        )
        
    norm_x, norm_y = projection_math.compute_normalized_coordinates(px_x, px_y, img_w, img_h)
    
    hfov, vfov = obs.camera_fov
    offset_x, offset_y = projection_math.compute_ground_offset(
        norm_x, norm_y, hfov, vfov, obs.altitude, obs.camera_mount_angle
    )
    
    east, north = projection_math.rotate_to_enu(offset_x, offset_y, obs.heading)
    lat, lon = projection_math.add_enu_to_wgs84(obs.latitude, obs.longitude, east, north)
    
    dist_m = math.sqrt(east**2 + north**2)
    
    # Bearing from drone to the projected point
    bearing_deg = (math.degrees(math.atan2(east, north)) + 360.0) % 360.0
    
    err = projection_math.estimate_error(px_x, px_y, obs.altitude, hfov, img_w)
    
    return ProjectionResult(
        latitude=lat,
        longitude=lon,
        ground_offset_x_m=offset_x,
        ground_offset_y_m=offset_y,
        ground_distance_m=dist_m,
        bearing_deg=bearing_deg,
        estimated_error_m=err,
        projection_timestamp=time.time()
    )
