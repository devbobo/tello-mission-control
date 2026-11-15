import numpy as np
import pytest
from aiortc import RTCSessionDescription

from app.models.video import WebRTCIceServer
from app.services import webrtc_service as webrtc_module
from app.services.webrtc_service import TelloVideoTrack, WebRTCService


class FakePeerConnection:
    def __init__(self):
        self.connectionState = "new"
        self.localDescription = None
        self.track = None
        self.handlers = {}
        self.closed = False
        self.configuration = None

    def addTrack(self, track):
        self.track = track

    def on(self, event):
        def register(handler):
            self.handlers[event] = handler
            return handler

        return register

    async def setRemoteDescription(self, description):
        self.remote_description = description

    async def createAnswer(self):
        return RTCSessionDescription(
            sdp=(
                "v=0\r\n"
                "a=candidate:1 1 UDP 123 172.18.0.2 40000 typ host generation 0\r\n"
                "a=candidate:2 1 UDP 123 192.0.2.1 40001 typ srflx generation 0\r\n"
            ),
            type="answer",
        )

    async def setLocalDescription(self, description):
        self.localDescription = description

    async def close(self):
        self.closed = True
        self.connectionState = "closed"


@pytest.mark.asyncio
async def test_webrtc_answer_starts_video_and_closes_peers(
    drone_manager, monkeypatch
):
    dm = drone_manager
    await dm.connect()
    peer = FakePeerConnection()

    def create_peer(**kwargs):
        peer.configuration = kwargs["configuration"]
        return peer

    monkeypatch.setattr(webrtc_module, "RTCPeerConnection", create_peer)
    service = WebRTCService(
        dm,
        fps=30,
        ice_servers=[WebRTCIceServer(urls="stun:stun.example.test")],
    )

    answer = await service.create_answer("browser-offer", "tello.local")

    assert answer["type"] == "answer"
    assert answer["peer_id"]
    assert "tello.local 40000 typ host" in answer["sdp"]
    assert "192.0.2.1 40001 typ srflx" in answer["sdp"]
    assert isinstance(peer.track, TelloVideoTrack)
    assert dm.is_streaming is True
    assert peer.configuration.iceServers[0].urls == "stun:stun.example.test"

    await service.close_all()
    assert peer.closed is True


@pytest.mark.asyncio
async def test_video_track_encodes_drone_frames():
    class FrameSource:
        def get_frame(self):
            return np.full((2, 3, 3), 127, dtype=np.uint8)

    track = TelloVideoTrack(FrameSource(), fps=30)
    frame = await track.recv()
    assert frame.width == 3
    assert frame.height == 2
    assert frame.to_ndarray(format="bgr24").tolist() == [
        [[127, 127, 127]] * 3,
        [[127, 127, 127]] * 3,
    ]
