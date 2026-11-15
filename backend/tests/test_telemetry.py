import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.models.odometry import OdometryData, OdometryMessage
from app.models.vision import VisionDetection, VisionFrameData, VisionMessage
from app.routers.telemetry import telemetry_ws


def test_websocket_connect_and_receive(test_client: TestClient):
    """Telemetry frame should contain all expected fields."""
    test_client.post("/api/control/connect")

    with test_client.websocket_connect("/api/ws/telemetry") as ws:
        data = ws.receive_json(mode="text")
        assert data["type"] == "telemetry"
        assert "timestamp" in data

        d = data["data"]
        assert "battery" in d
        assert "height" in d
        assert "flight_time" in d
        assert "temperature" in d
        assert "attitude" in d
        assert "speed" in d
        assert "barometer" in d
        assert "tof_distance" in d


def test_telemetry_nested_structure(test_client: TestClient):
    """Temperature, attitude, and speed should have correct nested keys."""
    test_client.post("/api/control/connect")

    with test_client.websocket_connect("/api/ws/telemetry") as ws:
        data = ws.receive_json(mode="text")
        d = data["data"]

        assert "high" in d["temperature"]
        assert "low" in d["temperature"]

        assert "pitch" in d["attitude"]
        assert "roll" in d["attitude"]
        assert "yaw" in d["attitude"]

        assert "x" in d["speed"]
        assert "y" in d["speed"]
        assert "z" in d["speed"]


def test_telemetry_values_types(test_client: TestClient):
    """Verify telemetry values have correct types."""
    test_client.post("/api/control/connect")

    with test_client.websocket_connect("/api/ws/telemetry") as ws:
        data = ws.receive_json(mode="text")
        d = data["data"]

        assert isinstance(d["battery"], int)
        assert isinstance(d["height"], int)
        assert isinstance(d["flight_time"], int)
        assert isinstance(d["temperature"]["high"], (int, float))
        assert isinstance(d["temperature"]["low"], (int, float))
        assert isinstance(d["attitude"]["pitch"], int)
        assert isinstance(d["attitude"]["roll"], int)
        assert isinstance(d["attitude"]["yaw"], int)
        assert isinstance(d["speed"]["x"], int)
        assert isinstance(d["speed"]["y"], int)
        assert isinstance(d["speed"]["z"], int)
        assert isinstance(d["barometer"], (int, float))
        assert isinstance(d["tof_distance"], int)


def test_telemetry_initial_values(test_client: TestClient):
    """Before takeoff, height/speed/barometer should be zero."""
    test_client.post("/api/control/connect")

    with test_client.websocket_connect("/api/ws/telemetry") as ws:
        data = ws.receive_json(mode="text")
        d = data["data"]

        assert d["battery"] == 85
        assert d["height"] == 0
        assert d["speed"]["x"] == 0
        assert d["speed"]["y"] == 0
        assert d["speed"]["z"] == 0
        assert d["barometer"] == 0.0
        assert d["tof_distance"] == 0
        assert d["attitude"]["yaw"] == 0


def test_telemetry_after_takeoff(test_client: TestClient):
    """After takeoff, height and barometer should be non-zero."""
    test_client.post("/api/control/connect")
    test_client.post("/api/control/takeoff")

    with test_client.websocket_connect("/api/ws/telemetry") as ws:
        data = ws.receive_json(mode="text")
        d = data["data"]

        assert d["height"] == 50
        assert d["barometer"] == 50.0
        assert d["tof_distance"] == 50


def test_telemetry_after_rotation(test_client: TestClient):
    """Yaw should change after rotation."""
    test_client.post("/api/control/connect")
    test_client.post("/api/control/takeoff")
    test_client.post(
        "/api/control/rotate",
        json={"direction": "cw", "angle_deg": 90},
    )

    with test_client.websocket_connect("/api/ws/telemetry") as ws:
        data = ws.receive_json(mode="text")
        assert data["data"]["attitude"]["yaw"] == 90


def test_telemetry_temperature_range(test_client: TestClient):
    """Temperature high should be >= low."""
    test_client.post("/api/control/connect")

    with test_client.websocket_connect("/api/ws/telemetry") as ws:
        data = ws.receive_json(mode="text")
        temp = data["data"]["temperature"]
        assert temp["high"] >= temp["low"]


def test_websocket_receives_command_log(test_client: TestClient):
    test_client.post("/api/control/connect")

    with test_client.websocket_connect("/api/ws/telemetry") as ws:
        test_client.post("/api/control/takeoff")

        found_command_log = False
        for _ in range(20):
            data = ws.receive_json(mode="text")
            if data["type"] == "command_log":
                assert data["data"]["command"] == "takeoff"
                assert "timestamp" in data["data"]
                found_command_log = True
                break

        assert found_command_log, "Expected a command_log message for takeoff"


def test_command_log_structure(test_client: TestClient):
    """Command log entries should have command, params, result, and timestamp."""
    test_client.post("/api/control/connect")
    test_client.post("/api/control/takeoff")

    with test_client.websocket_connect("/api/ws/telemetry") as ws:
        test_client.post(
            "/api/control/move",
            json={"direction": "forward", "distance_cm": 100},
        )

        for _ in range(20):
            data = ws.receive_json(mode="text")
            if data["type"] == "command_log" and data["data"]["command"] == "move":
                entry = data["data"]
                assert entry["params"]["direction"] == "forward"
                assert entry["params"]["distance_cm"] == 100
                assert entry["result"] == "ok"
                assert "timestamp" in entry
                break
        else:
            pytest.fail("Expected a command_log message for move")


def test_multiple_telemetry_frames(test_client: TestClient):
    """Should receive multiple telemetry frames in sequence."""
    test_client.post("/api/control/connect")

    with test_client.websocket_connect("/api/ws/telemetry") as ws:
        frames = []
        for _ in range(5):
            data = ws.receive_json(mode="text")
            if data["type"] == "telemetry":
                frames.append(data)
            if len(frames) >= 3:
                break

        assert len(frames) >= 3, f"Expected at least 3 telemetry frames, got {len(frames)}"


@pytest.mark.asyncio
async def test_websocket_serializes_vision_messages():
    class FakeService:
        def __init__(self):
            self.callback = None

        def subscribe(self, callback):
            self.callback = callback

        def unsubscribe(self, callback):
            assert callback == self.callback

    class FakeDroneManager:
        def add_command_log_callback(self, callback):
            self.callback = callback

        def remove_command_log_callback(self, callback):
            assert callback == self.callback

    class FakeWebSocket:
        def __init__(self):
            self.app = SimpleNamespace(
                state=SimpleNamespace(
                    telemetry_service=FakeService(),
                    vision_service=FakeService(),
                    odometry_service=FakeService(),
                    drone_manager=FakeDroneManager(),
                )
            )
            self.sent = []

        async def accept(self):
            pass

        async def receive_text(self):
            raise WebSocketDisconnect()

        async def send_text(self, text):
            self.sent.append(text)

    websocket = FakeWebSocket()
    await telemetry_ws(websocket)
    message = VisionMessage(
        data=VisionFrameData(
            frame_id=1,
            frame_width=960,
            frame_height=720,
            model="test-model",
            device="cpu",
            inference_ms=12.5,
            detections=[
                VisionDetection(
                    label="person",
                    confidence=0.8,
                    x_min=0.1,
                    y_min=0.2,
                    x_max=0.5,
                    y_max=0.7,
                )
            ],
        ),
        timestamp="2026-11-15T00:00:00Z",
    )

    await websocket.app.state.vision_service.callback(message)
    odometry = OdometryMessage(
        data=OdometryData(
            frame_id=2,
            frame_width=960,
            frame_height=720,
            position_x=0.01,
            position_y=-0.02,
            delta_x=0.01,
            delta_y=-0.02,
            tracking_valid=True,
            tracked_points=18,
            quality=0.8,
        ),
        timestamp="2026-11-15T00:00:00Z",
    )
    await websocket.app.state.odometry_service.callback(odometry)

    assert json.loads(websocket.sent[0]) == json.loads(message.model_dump_json())
    assert json.loads(websocket.sent[1]) == json.loads(odometry.model_dump_json())
