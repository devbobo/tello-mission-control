from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.config import settings
from app.models.video import WebRTCIceServer


def test_stream_start_requires_connection(test_client: TestClient):
    resp = test_client.post("/api/video/stream/start")
    assert resp.status_code == 409


def test_stream_start_and_stop(test_client: TestClient):
    test_client.post("/api/control/connect")

    resp = test_client.post("/api/video/stream/start")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    resp = test_client.post("/api/video/stream/stop")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_stream_start_idempotent(test_client: TestClient):
    test_client.post("/api/control/connect")
    test_client.post("/api/video/stream/start")

    resp = test_client.post("/api/video/stream/start")
    assert resp.status_code == 200
    assert "already" in resp.json()["message"].lower()


def test_snapshot_requires_connection(test_client: TestClient):
    resp = test_client.post("/api/video/snapshot")
    assert resp.status_code == 409


def test_snapshot_returns_jpeg(test_client: TestClient):
    test_client.post("/api/control/connect")

    resp = test_client.post("/api/video/snapshot")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    # JPEG files start with FF D8
    assert resp.content[:2] == b"\xff\xd8"


def test_webrtc_offer_requires_connection(test_client: TestClient):
    resp = test_client.post(
        "/api/video/webrtc/offer",
        json={"sdp": "browser-offer", "type": "offer"},
    )
    assert resp.status_code == 409


def test_webrtc_config_returns_ice_servers(test_client: TestClient, monkeypatch):
    monkeypatch.setattr(
        settings,
        "webrtc_ice_servers",
        [WebRTCIceServer(urls="stun:stun.example.test")],
    )

    resp = test_client.get("/api/video/webrtc/config")

    assert resp.status_code == 200
    assert resp.json() == {"iceServers": [{"urls": "stun:stun.example.test"}]}


def test_webrtc_offer_returns_peer_answer(test_client: TestClient, monkeypatch):
    service = test_client.app.state.webrtc_service
    create_answer = AsyncMock(
        return_value={"sdp": "browser-answer", "type": "answer", "peer_id": "peer-1"}
    )
    monkeypatch.setattr(service, "create_answer", create_answer)
    monkeypatch.setattr(settings, "webrtc_public_host", None)

    resp = test_client.post(
        "/api/video/webrtc/offer",
        json={"sdp": "browser-offer", "type": "offer"},
    )

    assert resp.status_code == 200
    assert resp.json() == {
        "sdp": "browser-answer",
        "type": "answer",
        "peer_id": "peer-1",
    }
    create_answer.assert_awaited_once_with("browser-offer", "testserver")


def test_webrtc_offer_uses_browser_origin_host(test_client: TestClient, monkeypatch):
    service = test_client.app.state.webrtc_service
    create_answer = AsyncMock(
        return_value={"sdp": "browser-answer", "type": "answer", "peer_id": "peer-1"}
    )
    monkeypatch.setattr(service, "create_answer", create_answer)
    monkeypatch.setattr(settings, "webrtc_public_host", None)

    resp = test_client.post(
        "/api/video/webrtc/offer",
        json={"sdp": "browser-offer", "type": "offer"},
        headers={"Origin": "http://controller.local:3000"},
    )

    assert resp.status_code == 200
    create_answer.assert_awaited_once_with("browser-offer", "controller.local")


def test_webrtc_peer_can_be_closed(test_client: TestClient, monkeypatch):
    service = test_client.app.state.webrtc_service
    close_peer = AsyncMock()
    monkeypatch.setattr(service, "close_peer", close_peer)

    resp = test_client.delete("/api/video/webrtc/peer-1")

    assert resp.status_code == 204
    close_peer.assert_awaited_once_with("peer-1")


def test_mjpeg_stream_endpoint_removed(test_client: TestClient):
    assert test_client.get("/api/video/stream").status_code == 404


def test_status_includes_streaming(test_client: TestClient):
    resp = test_client.get("/api/status")
    assert "streaming" in resp.json()

    test_client.post("/api/control/connect")
    test_client.post("/api/video/stream/start")

    resp = test_client.get("/api/status")
    assert resp.json()["streaming"] is True
