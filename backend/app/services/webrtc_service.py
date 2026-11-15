from __future__ import annotations

import asyncio
import logging
import re
import uuid
from fractions import Fraction

from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
    VideoStreamTrack,
)
from aiortc.mediastreams import MediaStreamError, VIDEO_CLOCK_RATE
from av import VideoFrame

from app.models.video import WebRTCIceServer
from app.services.drone_manager import DroneManager

logger = logging.getLogger(__name__)


class TelloVideoTrack(VideoStreamTrack):
    def __init__(self, drone_manager: DroneManager, fps: int) -> None:
        super().__init__()
        self._drone_manager = drone_manager
        self._fps = fps
        self._started_at: float | None = None
        self._frame_index = 0

    async def next_timestamp(self) -> tuple[int, Fraction]:
        if self.readyState != "live":
            raise MediaStreamError

        loop = asyncio.get_running_loop()
        if self._started_at is None:
            self._started_at = loop.time()
        else:
            self._frame_index += 1
            timestamp = self._frame_index / self._fps
            await asyncio.sleep(max(0, self._started_at + timestamp - loop.time()))

        pts = int(self._frame_index * VIDEO_CLOCK_RATE / self._fps)
        return pts, Fraction(1, VIDEO_CLOCK_RATE)

    async def recv(self) -> VideoFrame:
        frame = self._drone_manager.get_frame()
        while frame is None:
            if self.readyState != "live":
                raise MediaStreamError
            await asyncio.sleep(0.01)
            frame = self._drone_manager.get_frame()

        pts, time_base = await self.next_timestamp()
        video_frame = VideoFrame.from_ndarray(frame.copy(), format="bgr24")
        video_frame.pts = pts
        video_frame.time_base = time_base
        return video_frame


class WebRTCService:
    def __init__(
        self,
        drone_manager,
        fps: int,
        public_host: str | None = None,
        ice_servers: list[WebRTCIceServer] | None = None,
    ) -> None:
        if fps <= 0:
            raise ValueError("Video frame rate must be greater than zero")
        self._drone_manager = drone_manager
        self._fps = fps
        self._public_host = public_host
        self._ice_servers = [
            RTCIceServer(
                urls=server.urls,
                username=server.username,
                credential=server.credential,
            )
            for server in ice_servers or []
        ]
        self._peers: dict[str, RTCPeerConnection] = {}
        self._lock = asyncio.Lock()

    async def create_answer(
        self, offer_sdp: str, public_host: str
    ) -> dict[str, str]:
        if not self._drone_manager.is_streaming:
            await self._drone_manager.stream_on()

        peer_id = str(uuid.uuid4())
        peer = RTCPeerConnection(
            configuration=RTCConfiguration(iceServers=self._ice_servers)
        )
        async with self._lock:
            self._peers[peer_id] = peer

        @peer.on("connectionstatechange")
        async def on_connection_state_change() -> None:
            if peer.connectionState in {"failed", "closed"}:
                await self.close_peer(peer_id)

        try:
            peer.addTrack(TelloVideoTrack(self._drone_manager, self._fps))
            await peer.setRemoteDescription(
                RTCSessionDescription(sdp=offer_sdp, type="offer")
            )
            answer = await peer.createAnswer()
            await peer.setLocalDescription(answer)
            local_description = peer.localDescription
            if local_description is None:
                raise RuntimeError("WebRTC answer was not created")
            return {
                "sdp": self._advertise_host(local_description.sdp, public_host),
                "type": "answer",
                "peer_id": peer_id,
            }
        except Exception:
            await self.close_peer(peer_id)
            raise

    async def close_peer(self, peer_id: str) -> None:
        async with self._lock:
            peer = self._peers.pop(peer_id, None)
        if peer is not None and peer.connectionState != "closed":
            await peer.close()

    async def close_all(self) -> None:
        async with self._lock:
            peer_ids = list(self._peers)
        await asyncio.gather(*(self.close_peer(peer_id) for peer_id in peer_ids))

    def _advertise_host(self, sdp: str, request_host: str) -> str:
        host = self._public_host or request_host
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", host):
            raise ValueError("WebRTC public host contains invalid characters")

        lines = sdp.splitlines()
        for index, line in enumerate(lines):
            if not line.startswith("a=candidate:"):
                continue
            fields = line.split()
            if len(fields) > 7 and fields[6] == "typ" and fields[7] == "host":
                fields[4] = host
                lines[index] = " ".join(fields)
        return "\r\n".join(lines) + "\r\n"
