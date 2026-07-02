"""WebRTC peer-connection lifecycle and the camera-backed video track.

Why one source track + MediaRelay instead of one VideoCapture-reading track
per client: `aiortc.contrib.media.MediaRelay` is the framework's intended
fan-out primitive — a single upstream `MediaStreamTrack` is read once per
frame interval and distributed to any number of subscriber tracks, one per
peer connection. That guarantees the `Camera` is consulted at a single
cadence no matter how many browsers are watching, and that a slow or closed
client can't affect frame delivery to the others.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from fractions import Fraction
from typing import Callable, Dict, Optional

import numpy as np
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from aiortc.mediastreams import VideoStreamTrack
from av import VideoFrame

from backend.config import CameraConfig
from backend.services.camera import Camera, make_placeholder_frame
from backend.utils.logger import get_logger

logger = get_logger(__name__)

# RTP video clock rate per RFC 3551 / WebRTC convention. Defined locally
# (rather than relying on configured fps) so pts math is correct regardless
# of the camera's configured frame rate.
_VIDEO_CLOCK_RATE = 90000
_VIDEO_TIME_BASE = Fraction(1, _VIDEO_CLOCK_RATE)

# Seam for future frame post-processing (YOLO boxes, telemetry overlay,
# mission status text, recording taps) without any browser-side change.
# Unused today — intentionally not implemented, per project scope.
FrameProcessor = Callable[[np.ndarray], np.ndarray]


class CameraVideoStreamTrack(VideoStreamTrack):
    """Bridges the shared `Camera` to an aiortc-encodable track.

    Paces frames to the camera's *configured* fps using our own clock
    instead of the aiortc base class's fixed 30fps `next_timestamp()`, since
    a future low-power/OV9281 profile may run at a different rate.
    """

    def __init__(
        self,
        camera: Camera,
        fps: int,
        frame_processor: Optional[FrameProcessor] = None,
    ) -> None:
        super().__init__()
        self._camera = camera
        self._fps = max(1, fps)
        self._frame_processor = frame_processor
        self._frame_index = 0
        self._start_time: Optional[float] = None

    async def recv(self) -> VideoFrame:
        pts, time_base = await self._next_timestamp()

        frame_array = self._camera.get_frame()
        if frame_array is None:
            frame_array = make_placeholder_frame(
                self._camera.config.width, self._camera.config.height
            )

        if self._frame_processor is not None:
            frame_array = self._frame_processor(frame_array)

        video_frame = VideoFrame.from_ndarray(frame_array, format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame

    async def _next_timestamp(self) -> tuple[int, Fraction]:
        if self._start_time is None:
            self._start_time = time.time()
        else:
            self._frame_index += 1

        target_time = self._start_time + (self._frame_index / self._fps)
        wait = target_time - time.time()
        if wait > 0:
            await asyncio.sleep(wait)

        pts = int(self._frame_index * (_VIDEO_CLOCK_RATE / self._fps))
        return pts, _VIDEO_TIME_BASE


class WebRTCManager:
    """Owns every `RTCPeerConnection` and the single camera source track."""

    def __init__(self, camera: Camera, camera_config: CameraConfig) -> None:
        self._camera = camera
        self._relay = MediaRelay()
        self._source_track = CameraVideoStreamTrack(camera, fps=camera_config.fps)
        self._peer_connections: Dict[str, RTCPeerConnection] = {}
        self._lock = asyncio.Lock()

    async def create_peer_connection(self, sdp: str, type_: str) -> RTCSessionDescription:
        """Negotiate a new peer connection for one browser client.

        No STUN/TURN servers are configured: the project runs entirely on a
        local network with no internet dependency, so host ICE candidates
        are sufficient.
        """
        pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[]))
        pc_id = str(uuid.uuid4())

        async with self._lock:
            self._peer_connections[pc_id] = pc

        @pc.on("connectionstatechange")
        async def on_connectionstatechange() -> None:
            logger.info("Peer %s connection state -> %s", pc_id, pc.connectionState)
            if pc.connectionState in ("failed", "closed"):
                await self._cleanup_peer(pc_id)

        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange() -> None:
            logger.info("Peer %s ICE state -> %s", pc_id, pc.iceConnectionState)
            # "disconnected" is left alone deliberately: ICE may recover from
            # a transient drop on its own. Only "failed" (the terminal state
            # the ICE agent reaches once recovery is given up on) triggers
            # cleanup, so a brief Wi-Fi blip doesn't tear down the session.
            if pc.iceConnectionState == "failed":
                await self._cleanup_peer(pc_id)

        pc.addTrack(self._relay.subscribe(self._source_track))

        offer = RTCSessionDescription(sdp=sdp, type=type_)
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        logger.info("Peer %s offer/answer negotiated", pc_id)
        return pc.localDescription

    async def _cleanup_peer(self, pc_id: str) -> None:
        async with self._lock:
            pc = self._peer_connections.pop(pc_id, None)
        if pc is not None:
            await pc.close()
            logger.info("Peer %s closed and removed", pc_id)

    async def shutdown(self) -> None:
        """Close every peer connection. Called once from app lifespan shutdown."""
        async with self._lock:
            peer_connections = list(self._peer_connections.values())
            self._peer_connections.clear()

        await asyncio.gather(
            *(pc.close() for pc in peer_connections), return_exceptions=True
        )
        logger.info("WebRTCManager shutdown: closed %d peer connection(s)", len(peer_connections))

    def get_status(self) -> dict:
        return {
            "peer_count": len(self._peer_connections),
            "peers": [
                {
                    "connection_state": pc.connectionState,
                    "ice_connection_state": pc.iceConnectionState,
                }
                for pc in self._peer_connections.values()
            ],
        }
