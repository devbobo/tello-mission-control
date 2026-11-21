import asyncio
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.models.telemetry import (
    AttitudeData,
    SpeedData,
    TelemetryData,
    TelemetryFrame,
    TemperatureData,
)
from app.services.auto_recording_service import (
    AutoRecordingError,
    AutoRecordingService,
)


def telemetry_frame(
    height: int, speed_x: int = 0, speed_y: int = 0, speed_z: int = 0
) -> TelemetryFrame:
    return TelemetryFrame(
        data=TelemetryData(
            battery=85,
            height=height,
            flight_time=0,
            temperature=TemperatureData(high=20, low=18),
            attitude=AttitudeData(pitch=0, roll=0, yaw=0),
            speed=SpeedData(x=speed_x, y=speed_y, z=speed_z),
            barometer=0,
            tof_distance=0,
        ),
        timestamp=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_takeoff_recording_requires_a_ready_browser_recorder():
    service = AutoRecordingService()

    with pytest.raises(AutoRecordingError, match="connected, ready browser recorder"):
        await service.start_recording_for_takeoff()


@pytest.mark.asyncio
async def test_takeoff_recording_waits_for_browser_acknowledgement():
    service = AutoRecordingService()
    request_sent = asyncio.Event()
    requests: list[dict] = []
    recorder_id = ""

    async def send(message: dict):
        requests.append(message)
        request_sent.set()

    recorder_id = service.connect_recorder(send)
    service.handle_client_message(
        recorder_id, {"type": "recorder_status", "data": {"ready": True}}
    )

    start_request = asyncio.create_task(service.start_recording_for_takeoff())
    await asyncio.wait_for(request_sent.wait(), timeout=1)
    assert not start_request.done()
    request_id = requests[0]["data"]["request_id"]

    service.handle_client_message(
        recorder_id,
        {
            "type": "recording_ack",
            "data": {"request_id": request_id, "ok": True},
        },
    )
    await start_request


@pytest.mark.asyncio
async def test_landing_stops_recording_only_after_low_height_and_speed_samples():
    service = AutoRecordingService()
    actions: list[str] = []
    recorder_id = ""

    async def send(message: dict):
        request = message["data"]
        actions.append(request["action"])
        service.handle_client_message(
            recorder_id,
            {
                "type": "recording_ack",
                "data": {"request_id": request["request_id"], "ok": True},
            },
        )

    recorder_id = service.connect_recorder(send)
    service.handle_client_message(
        recorder_id, {"type": "recorder_status", "data": {"ready": True}}
    )
    await service.start_recording_for_takeoff()
    service.monitor_landing_from_height(baseline_height=50)

    await service.handle_telemetry(telemetry_frame(70))
    for _ in range(3):
        await service.handle_telemetry(telemetry_frame(50, speed_x=15))
    assert actions == ["start"]

    await service.handle_telemetry(telemetry_frame(60))
    for _ in range(3):
        await service.handle_telemetry(telemetry_frame(-5, speed_x=1))
    for _ in range(7):
        await service.handle_telemetry(telemetry_frame(-5))
    assert actions == ["start"]

    await service.handle_telemetry(telemetry_frame(-5))
    assert service._stop_task is not None
    await service._stop_task
    assert actions == ["start", "stop"]


@pytest.mark.asyncio
async def test_landing_threshold_and_hold_samples_are_configurable(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(settings, "auto_record_landing_speed_threshold_cm_s", 4)
    monkeypatch.setattr(settings, "auto_record_landing_confirmation_samples", 2)
    service = AutoRecordingService()
    actions: list[str] = []
    recorder_id = ""

    async def send(message: dict):
        request = message["data"]
        actions.append(request["action"])
        service.handle_client_message(
            recorder_id,
            {
                "type": "recording_ack",
                "data": {"request_id": request["request_id"], "ok": True},
            },
        )

    recorder_id = service.connect_recorder(send)
    service.handle_client_message(
        recorder_id, {"type": "recorder_status", "data": {"ready": True}}
    )
    await service.start_recording_for_takeoff()
    service.monitor_landing_from_height(baseline_height=50)
    await service.handle_telemetry(telemetry_frame(70))

    await service.handle_telemetry(telemetry_frame(50, speed_x=4))
    assert actions == ["start"]
    await service.handle_telemetry(telemetry_frame(50, speed_x=4))

    assert service._stop_task is not None
    await service._stop_task
    assert actions == ["start", "stop"]


def test_auto_takeoff_is_blocked_when_browser_recorder_is_unavailable(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "auto_record_on_takeoff", True)
    assert test_client.post("/api/control/connect").status_code == 200

    response = test_client.post("/api/control/takeoff")

    assert response.status_code == 503
    assert "browser recorder" in response.json()["detail"]
    assert test_client.get("/api/status").json()["flying"] is False


def test_auto_takeoff_starts_only_after_recorder_acknowledges_start(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "auto_record_on_takeoff", True)
    assert test_client.post("/api/control/connect").status_code == 200
    service: AutoRecordingService = app.state.auto_recording_service
    manager = app.state.drone_manager
    actions: list[tuple[str, bool]] = []
    recorder_id = ""

    async def send(message: dict):
        request = message["data"]
        actions.append((request["action"], manager._flying))
        service.handle_client_message(
            recorder_id,
            {
                "type": "recording_ack",
                "data": {"request_id": request["request_id"], "ok": True},
            },
        )

    recorder_id = service.connect_recorder(send)
    service.handle_client_message(
        recorder_id, {"type": "recorder_status", "data": {"ready": True}}
    )

    response = test_client.post("/api/control/takeoff")

    assert response.status_code == 200
    assert actions == [("start", False)]
    assert test_client.get("/api/status").json()["flying"] is True


def test_takeoff_waits_for_recording_ack_and_rejects_failed_start(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "auto_record_on_takeoff", True)
    assert test_client.post("/api/control/connect").status_code == 200
    service: AutoRecordingService = app.state.auto_recording_service
    manager = app.state.drone_manager
    actions: list[tuple[str, bool]] = []
    recorder_id = ""

    async def send(message: dict):
        request = message["data"]
        actions.append((request["action"], manager._flying))
        service.handle_client_message(
            recorder_id,
            {
                "type": "recording_ack",
                "data": {
                    "request_id": request["request_id"],
                    "ok": request["action"] != "start",
                    "error": "Recorder failed to start",
                },
            },
        )

    recorder_id = service.connect_recorder(send)
    service.handle_client_message(
        recorder_id, {"type": "recorder_status", "data": {"ready": True}}
    )

    response = test_client.post("/api/control/takeoff")

    assert response.status_code == 503
    assert response.json()["detail"] == "Recorder failed to start"
    assert actions == [("start", False)]
    assert test_client.get("/api/status").json()["flying"] is False


def test_recording_is_stopped_if_drone_takeoff_fails(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "auto_record_on_takeoff", True)
    assert test_client.post("/api/control/connect").status_code == 200
    service: AutoRecordingService = app.state.auto_recording_service
    manager = app.state.drone_manager
    actions: list[str] = []
    recorder_id = ""

    async def send(message: dict):
        request = message["data"]
        actions.append(request["action"])
        service.handle_client_message(
            recorder_id,
            {
                "type": "recording_ack",
                "data": {"request_id": request["request_id"], "ok": True},
            },
        )

    async def fail_takeoff():
        raise RuntimeError("takeoff failed")

    monkeypatch.setattr(manager, "takeoff", fail_takeoff)
    recorder_id = service.connect_recorder(send)
    service.handle_client_message(
        recorder_id, {"type": "recorder_status", "data": {"ready": True}}
    )

    response = test_client.post("/api/control/takeoff")

    assert response.status_code == 500
    assert actions == ["start", "stop"]
