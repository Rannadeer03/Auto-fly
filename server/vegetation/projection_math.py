"""Mathematical models for camera projection.

Converts pixel offsets into ground offsets using camera intrinsic and
extrinsic parameters, assuming a flat ground model.
"""

import math
from typing import Tuple

def compute_pixel_offset(cx: float, cy: float, img_w: int, img_h: int) -> Tuple[float, float]:
    """Calculate pixel offset from the image center."""
    return cx - (img_w / 2.0), cy - (img_h / 2.0)

def compute_normalized_coordinates(px_x: float, px_y: float, img_w: int, img_h: int) -> Tuple[float, float]:
    """Convert pixel offset to normalized image coordinates [-1, 1]."""
    return px_x / (img_w / 2.0), px_y / (img_h / 2.0)

def compute_ground_offset(
    norm_x: float, norm_y: float,
    hfov_deg: float, vfov_deg: float,
    altitude_m: float, pitch_deg: float
) -> Tuple[float, float]:
    """Compute (Right, Forward) ground offsets in meters relative to drone.
    
    Uses standard pinhole projection rotated by the camera pitch.
    pitch_deg = -90 is nadir (looking straight down).
    pitch_deg = 0 is looking straight forward.
    """
    tan_hx = math.tan(math.radians(hfov_deg / 2.0))
    tan_hy = math.tan(math.radians(vfov_deg / 2.0))
    
    # Ray in camera frame (X=Right, Y=Down, Z=Forward into scene)
    v_c_x = norm_x * tan_hx
    v_c_y = norm_y * tan_hy
    v_c_z = 1.0
    
    p = math.radians(pitch_deg)
    
    # Rotate by pitch to drone body frame (X=Right, Y=Forward, Z=Down)
    # Rotation around X axis by pitch angle.
    v_body_x = v_c_x
    v_body_y = v_c_z * math.cos(p) + v_c_y * math.sin(p)
    v_body_z = -v_c_z * math.sin(p) + v_c_y * math.cos(p)
    
    # Avoid division by zero or negative Z (looking at sky/horizon)
    if v_body_z <= 0.001:
        return 0.0, 0.0
        
    S = altitude_m / v_body_z
    offset_x = S * v_body_x  # Right
    offset_y = S * v_body_y  # Forward
    
    return offset_x, offset_y

def rotate_to_enu(offset_x: float, offset_y: float, heading_deg: float) -> Tuple[float, float]:
    """Rotate drone body offset (Right, Forward) to ENU (East, North)."""
    h = math.radians(heading_deg)
    # heading 0 = North -> offset_y is North, offset_x is East
    # heading 90 = East -> offset_y is East, offset_x is South (-North)
    east = offset_x * math.cos(h) + offset_y * math.sin(h)
    north = -offset_x * math.sin(h) + offset_y * math.cos(h)
    return east, north

def add_enu_to_wgs84(lat: float, lon: float, east: float, north: float) -> Tuple[float, float]:
    """Add ENU offsets in meters to a WGS84 coordinate."""
    R_EARTH = 6378137.0
    d_lat = math.degrees(north / R_EARTH)
    # Avoid division by zero at poles
    cos_lat = math.cos(math.radians(lat))
    if abs(cos_lat) < 1e-6:
        cos_lat = 1e-6
    d_lon = math.degrees(east / (R_EARTH * cos_lat))
    return lat + d_lat, lon + d_lon

def estimate_error(
    px_x: float, px_y: float,
    altitude_m: float,
    hfov_deg: float, img_w: int
) -> float:
    """Estimate GPS uncertainty based on baseline error + geometric factors."""
    base_gps_error = 2.5
    if altitude_m <= 0 or img_w <= 0:
        return base_gps_error
        
    dist_px = math.sqrt(px_x**2 + px_y**2)
    # GSD at nadir center:
    gsd = (2.0 * altitude_m * math.tan(math.radians(hfov_deg / 2.0))) / float(img_w)
    
    # Simple linear heuristic: 10% projection uncertainty scaling based on distance
    projection_error = gsd * dist_px * 0.1
    return base_gps_error + projection_error
