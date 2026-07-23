"""EXIF metadata embedding for captured mission photos.

Standard EXIF/GPS tags are used wherever one exists (GIS software reads GPS
lat/lon/alt/heading straight out of these) so photos stay usable in QGIS,
ODM, Pix4D etc. even without metadata.json. DroneAI-specific fields that have
no standard EXIF tag (mission id, waypoint, sharpness scores, checksum) are
carried as a JSON blob in the standard UserComment tag, which is exactly what
that tag is for — no MakerNote/XMP writer needed for this camera.

The embedded record is built from the same dict storage_service.py writes to
metadata.json/csv, so EXIF and the JSON/CSV outputs can never drift apart.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import piexif
import piexif.helper

from config import settings

logger = logging.getLogger(__name__)


def _deg_to_dms_rational(deg: float) -> tuple:
    deg = abs(deg)
    d = int(deg)
    m_float = (deg - d) * 60
    m = int(m_float)
    s = round((m_float - m) * 60 * 100)
    return ((d, 1), (m, 1), (s, 100))


def _rational(value: float, precision: int = 1000) -> tuple:
    return (int(round(value * precision)), precision)


def build_exif_bytes(record: dict, width: int, height: int) -> bytes:
    """Build an EXIF byte blob for one captured photo from its metadata
    record (the same dict passed to storage_service.record_photo)."""
    lat = record.get("latitude", 0.0) or 0.0
    lon = record.get("longitude", 0.0) or 0.0
    alt = record.get("altitude_msl", 0.0) or 0.0
    heading = record.get("heading_deg", 0.0) or 0.0
    timestamp = record.get("timestamp", "")

    date_part, _, time_part = timestamp.partition("T")
    exif_date = date_part.replace("-", ":") if date_part else "0000:00:00"
    exif_time = time_part.rstrip("Z") if time_part else "00:00:00"

    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: "N" if lat >= 0 else "S",
        piexif.GPSIFD.GPSLatitude: _deg_to_dms_rational(lat),
        piexif.GPSIFD.GPSLongitudeRef: "E" if lon >= 0 else "W",
        piexif.GPSIFD.GPSLongitude: _deg_to_dms_rational(lon),
        piexif.GPSIFD.GPSAltitudeRef: 0 if alt >= 0 else 1,
        piexif.GPSIFD.GPSAltitude: _rational(abs(alt)),
        piexif.GPSIFD.GPSImgDirectionRef: "T",
        piexif.GPSIFD.GPSImgDirection: _rational(heading % 360.0),
        piexif.GPSIFD.GPSSpeedRef: "K",
        piexif.GPSIFD.GPSSpeed: _rational((record.get("drone_speed_ms", 0.0) or 0.0) * 3.6),
        piexif.GPSIFD.GPSSatellites: str(record.get("satellites_visible", 0)),
        piexif.GPSIFD.GPSDateStamp: exif_date,
    }

    user_comment = {
        "mission_id": record.get("mission_id"),
        "mission_name": record.get("mission_name"),
        "image_id": record.get("image_id"),
        "waypoint_number": record.get("waypoint_number"),
        "capture_sequence": record.get("capture_sequence"),
        "pitch_deg": record.get("pitch_deg"),
        "roll_deg": record.get("roll_deg"),
        "camera_orientation_deg": record.get("camera_orientation_deg"),
        "gps_fix_quality": record.get("gps_fix_quality"),
        "sharpness_laplacian": record.get("sharpness_laplacian"),
        "sharpness_tenengrad": record.get("sharpness_tenengrad"),
        "sharpness_brenner": record.get("sharpness_brenner"),
        "edge_density": record.get("edge_density"),
        "quality_confidence": record.get("quality_confidence"),
        "quality_passed": record.get("quality_passed"),
        "checksum_sha256": record.get("checksum_sha256"),
        "droneai_version": settings.DRONEAI_VERSION,
    }
    comment_bytes = piexif.helper.UserComment.dump(
        json.dumps(user_comment, default=str), encoding="unicode"
    )

    zeroth_ifd = {
        piexif.ImageIFD.Make: "DroneAI",
        piexif.ImageIFD.Model: settings.CAMERA_MODEL,
        piexif.ImageIFD.Software: f"DroneAI {settings.DRONEAI_VERSION}",
        piexif.ImageIFD.ImageDescription: record.get("mission_name", "")[:255],
        piexif.ImageIFD.DateTime: f"{exif_date} {exif_time}",
    }

    exif_ifd = {
        piexif.ExifIFD.DateTimeOriginal: f"{exif_date} {exif_time}",
        piexif.ExifIFD.DateTimeDigitized: f"{exif_date} {exif_time}",
        piexif.ExifIFD.PixelXDimension: width,
        piexif.ExifIFD.PixelYDimension: height,
        piexif.ExifIFD.LensModel: settings.CAMERA_LENS,
        piexif.ExifIFD.UserComment: comment_bytes,
    }

    exif_dict = {"0th": zeroth_ifd, "Exif": exif_ifd, "GPS": gps_ifd}
    return piexif.dump(exif_dict)


def embed_exif(path: Path, record: dict, width: int, height: int) -> bool:
    """Insert EXIF metadata into an already-written JPEG. Never raises —
    a failed embed must not fail the photo capture itself."""
    if not settings.EXIF_ENABLED:
        return False
    try:
        exif_bytes = build_exif_bytes(record, width, height)
        piexif.insert(exif_bytes, str(path))
        return True
    except Exception:
        logger.exception("EXIF embed failed for %s (photo kept without EXIF)", path)
        return False
