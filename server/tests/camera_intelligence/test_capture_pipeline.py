"""Integration test: CaptureStrategy._capture_one end to end — frame
selection/retry, disk write, checksum, metadata record, and EXIF embed all
wired together (services/capture_strategies.py, storage_service.py,
exif_service.py, image_quality.py). No camera hardware or MAVLink link
needed: camera_service.get_frame_with_ts is stubbed and drone_state is used
with its real (zeroed) defaults.
"""
import hashlib
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import cv2
import numpy as np
import piexif

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from config import settings
from services.camera_service import camera_service
from services.capture_strategies import HoverCaptureStrategy
from services.storage_service import MissionStorage


def make_sharp_frame(size: int = 480) -> np.ndarray:
    frame = np.zeros((size, size, 3), dtype=np.uint8)
    step = 8
    for y in range(0, size, step):
        for x in range(0, size, step):
            if ((x // step) + (y // step)) % 2 == 0:
                frame[y : y + step, x : x + step] = 255
    return frame


def make_blurred_frame(sharp: np.ndarray) -> np.ndarray:
    return cv2.GaussianBlur(sharp, (31, 31), sigmaX=15)


class _FakeFrameSource:
    def __init__(self, frame) -> None:
        self.frame = frame
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.frame, float(self.calls)


class _NoFrameSource:
    def __call__(self):
        return None, None


def run_tests() -> None:
    failures = []
    original_get_frame_with_ts = camera_service.get_frame_with_ts
    original_retry_limit = settings.CAPTURE_RETRY_LIMIT
    tmp_root = tempfile.mkdtemp()

    try:
        settings.CAPTURE_RETRY_LIMIT = 2
        sharp = make_sharp_frame()
        blurred = make_blurred_frame(sharp)

        # ── Happy path: sharp frame accepted on first attempt ──────────────
        storage = MissionStorage(
            root=Path(tmp_root) / "sharp",
            mission_id="Test_20260723_000000",
            mission_name="Test",
        )
        camera_service.get_frame_with_ts = _FakeFrameSource(sharp)
        strategy = HoverCaptureStrategy(capture_points={})
        ok = strategy._capture_one(storage, waypoint_number=3)

        if not ok:
            failures.append("Happy-path capture returned False.")
        if strategy.photos_captured != 1:
            failures.append(f"photos_captured={strategy.photos_captured}, expected 1")

        photo_path = storage.next_photo_path(1)
        if not photo_path.exists():
            failures.append(f"Photo file was not written: {photo_path}")
        else:
            record = storage._image_records[0]
            if not record.get("image_id"):
                failures.append("record missing image_id.")
            try:
                uuid.UUID(record["image_id"])
            except ValueError:
                failures.append(f"image_id is not a valid UUID: {record.get('image_id')}")
            if record.get("waypoint_number") != 3:
                failures.append(f"waypoint_number mismatch: {record.get('waypoint_number')}")
            if not record.get("quality_passed"):
                failures.append("Sharp frame recorded as quality_passed=False.")
            expected_checksum = hashlib.sha256(photo_path.read_bytes()).hexdigest()
            if record.get("checksum_sha256") != expected_checksum:
                failures.append("checksum_sha256 does not match actual file contents.")
            thumb_path = storage.thumb_path_for(photo_path)
            if not thumb_path.exists():
                failures.append(f"Thumbnail not written: {thumb_path}")

            exif = piexif.load(str(photo_path))
            if piexif.GPSIFD.GPSLatitudeRef not in exif["GPS"]:
                failures.append("EXIF GPS block missing on captured photo.")

        # ── Retry path: only blurred frames available -> still captured, ──
        # ── but flagged quality_passed=False, and every retry attempted. ──
        storage2 = MissionStorage(
            root=Path(tmp_root) / "blurred",
            mission_id="Test_20260723_000001",
            mission_name="Test",
        )
        fake_source = _FakeFrameSource(blurred)
        camera_service.get_frame_with_ts = fake_source
        strategy2 = HoverCaptureStrategy(capture_points={})
        ok2 = strategy2._capture_one(storage2, waypoint_number=1)

        if not ok2:
            failures.append("Retry-path capture returned False (should accept best-effort frame).")
        expected_calls = settings.CAPTURE_RETRY_LIMIT + 1
        if fake_source.calls != expected_calls:
            failures.append(
                f"get_frame_with_ts called {fake_source.calls} times, expected {expected_calls}."
            )
        if storage2._image_records and storage2._image_records[0].get("quality_passed"):
            failures.append("Blurred frame incorrectly recorded as quality_passed=True.")

        # ── No frame available -> failure recorded, nothing written ────────
        storage3 = MissionStorage(
            root=Path(tmp_root) / "none",
            mission_id="Test_20260723_000002",
            mission_name="Test",
        )
        camera_service.get_frame_with_ts = _NoFrameSource()
        strategy3 = HoverCaptureStrategy(capture_points={})
        ok3 = strategy3._capture_one(storage3, waypoint_number=1)
        if ok3:
            failures.append("Capture with no available frame returned True.")
        if strategy3.failed_captures != 1:
            failures.append(f"failed_captures={strategy3.failed_captures}, expected 1")
        if storage3._image_records:
            failures.append("A metadata record was written despite capture failure.")

    finally:
        camera_service.get_frame_with_ts = original_get_frame_with_ts
        settings.CAPTURE_RETRY_LIMIT = original_retry_limit
        shutil.rmtree(tmp_root, ignore_errors=True)

    print(f"Completed capture_pipeline checks. Failures: {len(failures)}")
    if failures:
        print("\n".join(failures))
        sys.exit(1)


if __name__ == "__main__":
    run_tests()
