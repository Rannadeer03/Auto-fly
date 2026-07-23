"""Unit tests for services/exif_service.py — verifies embedded EXIF/GPS
round-trips correctly and stays in sync with the metadata record it came
from (the same dict storage_service.py writes to metadata.json/csv)."""
import json
import os
import sys
import tempfile

import cv2
import numpy as np
import piexif
import piexif.helper

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from services.exif_service import embed_exif


def make_record() -> dict:
    return {
        "filename": "images/photo_00001.jpg",
        "image_id": "abc-123",
        "mission_name": "North_Field",
        "mission_id": "North_Field_20260723_120000",
        "timestamp": "2026-07-23T12:00:05Z",
        "latitude": 17.385044,
        "longitude": 78.486671,
        "altitude_rel": 30.0,
        "altitude_msl": 512.3,
        "heading_deg": 87.5,
        "pitch_deg": -1.2,
        "roll_deg": 0.4,
        "camera_orientation_deg": -90.0,
        "waypoint_number": 4,
        "capture_sequence": 4,
        "drone_speed_ms": 5.1,
        "gps_fix_quality": "3D Fix",
        "satellites_visible": 11,
        "sharpness_laplacian": 210.4,
        "sharpness_tenengrad": 1800.2,
        "sharpness_brenner": 2900.7,
        "edge_density": 0.12,
        "quality_confidence": 0.61,
        "quality_passed": True,
        "checksum_sha256": "deadbeef",
    }


def run_tests() -> None:
    failures = []

    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "photo.jpg")
        cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

        record = make_record()
        ok = embed_exif(path, record, width=320, height=240)
        if not ok:
            failures.append("embed_exif() returned False on a valid JPEG.")

        loaded = piexif.load(path)

        gps = loaded["GPS"]
        if gps.get(piexif.GPSIFD.GPSLatitudeRef) != b"N":
            failures.append(f"GPSLatitudeRef wrong: {gps.get(piexif.GPSIFD.GPSLatitudeRef)}")
        if gps.get(piexif.GPSIFD.GPSLongitudeRef) != b"E":
            failures.append(f"GPSLongitudeRef wrong: {gps.get(piexif.GPSIFD.GPSLongitudeRef)}")

        d, m, s = gps[piexif.GPSIFD.GPSLatitude]
        recovered_lat = d[0] / d[1] + (m[0] / m[1]) / 60 + (s[0] / s[1]) / 3600
        if abs(recovered_lat - record["latitude"]) > 1e-4:
            failures.append(f"Latitude round-trip off: {recovered_lat} vs {record['latitude']}")

        exif_ifd = loaded["Exif"]
        comment_raw = exif_ifd.get(piexif.ExifIFD.UserComment)
        if comment_raw is None:
            failures.append("UserComment missing from embedded EXIF.")
        else:
            decoded = piexif.helper.UserComment.load(comment_raw)
            payload = json.loads(decoded)
            if payload.get("mission_id") != record["mission_id"]:
                failures.append("UserComment mission_id did not round-trip.")
            if payload.get("checksum_sha256") != record["checksum_sha256"]:
                failures.append("UserComment checksum did not round-trip.")
            if payload.get("quality_confidence") != record["quality_confidence"]:
                failures.append("UserComment quality_confidence did not round-trip.")

        zeroth = loaded["0th"]
        if zeroth.get(piexif.ImageIFD.Model) is None:
            failures.append("Camera Model tag missing from 0th IFD.")

    print(f"Completed exif_service checks. Failures: {len(failures)}")
    if failures:
        print("\n".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
