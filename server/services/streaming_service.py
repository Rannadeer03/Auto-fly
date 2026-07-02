"""WebRTC live-streaming service.

Adapted from the Webcam project's backend/services/webrtc_manager.py.

One source track + MediaRelay: `aiortc.contrib.media.MediaRelay` reads the
single upstream `MediaStreamTrack` once per frame interval and fans it out to
any number of subscriber tracks, one per peer connection. The camera is
consulted at a single cadence no matter how many browsers are watching, and a
slow or closed client can't affect frame delivery to the others.

Streaming is fully independent from recording: both read published frames
from the shared CameraService but share no other state, so a streaming
failure never affects recording or the mission.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from fractions import Fraction
from typing import Dict, Optional

from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay
from aiortc.mediastreams import VideoStreamTrack
from av import VideoFrame

from config import settings
from services.camera_service import CameraService, camera_service, make_placeholder_frame

logger = logging.getLogger(__name__)

# RTP video clock rate per RFC 3551 / WebRTC convention.
_VIDEO_CLOCK_RATE = 90000
_VIDEO_TIME_BASE = Fraction(1, _VIDEO_CLOCK_RATE)


class CameraVideoStreamTrack(VideoStreamTrack):
    """Bridges the shared CameraService to an aiortc-encodable track.

    Paces frames to the camera's configured fps using our own clock instead
    of the aiortc base class's fixed 30fps `next_timestamp()`.
    """

    def __init__(self, camera: CameraService, fps: int) -> None:
        super().__init__()
        self._camera = camera
        self._fps = max(1, fps)
        self._frame_index = 0
        self._start_time: Optional[float] = None

    async def recv(self) -> VideoFrame:
        pts, time_base = await self._next_timestamp()

        frame_array = self._camera.get_frame()
        if frame_array is None:
            frame_array = make_placeholder_frame(
                settings.CAMERA_WIDTH, settings.CAMERA_HEIGHT
            )

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


class StreamingService:
    """Owns every `RTCPeerConnection` and the single camera source track."""

    def __init__(self, camera: CameraService) -> None:
        self._camera = camera
        self._relay = MediaRelay()
        self._source_track: Optional[CameraVideoStreamTrack] = None
        self._peer_connections: Dict[str, RTCPeerConnection] = {}
        self._lock = asyncio.Lock()

    def _get_source_track(self) -> CameraVideoStreamTrack:
        # Created lazily so importing this module never touches the event loop.
        if self._source_track is None:
            self._source_track = CameraVideoStreamTrack(
                self._camera, fps=settings.CAMERA_FPS
            )
        return self._source_track

    async def create_peer_connection(self, sdp: str, type_: str) -> RTCSessionDescription:
        """Negotiate a new peer connection for one browser client.

        No STUN/TURN servers: the Pi and the browser run on the same local
        network, so host ICE candidates are sufficient.
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
            # "disconnected" may recover on its own; only terminal "failed"
            # triggers cleanup, so a brief Wi-Fi blip doesn't kill the session.
            if pc.iceConnectionState == "failed":
                await self._cleanup_peer(pc_id)

        pc.addTrack(self._relay.subscribe(self._get_source_track()))

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
        logger.info(
            "StreamingService shutdown: closed %d peer connection(s)",
            len(peer_connections),
        )

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


# Module-level singleton
streaming_service = StreamingService(camera_service)
