import asyncio
from datetime import datetime, timezone
from threading import Event

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
async def test_successful_land_sends_only_one_stop_while_awaiting_acknowledgement():
    service = AutoRecordingService()
    requests: list[dict] = []
    sent = asyncio.Event()
    recorder_id = ""

    async def send(message: dict):
        request = message["data"]
        requests.append(request)
        if request["action"] == "start":
            service.handle_client_message(
                recorder_id,
                {
                    "type": "recording_ack",
                    "data": {"request_id": request["request_id"], "ok": True},
                },
            )
        else:
            sent.set()

    recorder_id = service.connect_recorder(send)
    service.handle_client_message(
        recorder_id, {"type": "recorder_status", "data": {"ready": True}}
    )
    await service.start_recording_for_takeoff()

    service.stop_recording_after_successful_land()
    await asyncio.wait_for(sent.wait(), timeout=1)
    service.stop_recording_after_successful_land()
    assert [request["action"] for request in requests] == ["start", "stop"]

    service.handle_client_message(
        recorder_id,
        {
            "type": "recording_ack",
            "data": {"request_id": requests[-1]["request_id"], "ok": True},
        },
    )
    assert service._stop_task is not None
    await service._stop_task
    service.stop_recording_after_successful_land()
    assert [request["action"] for request in requests] == ["start", "stop"]


@pytest.mark.asyncio
async def test_next_takeoff_waits_for_previous_recording_stop():
    service = AutoRecordingService()
    requests: list[dict] = []
    sent = asyncio.Event()
    recorder_id = ""

    async def send(message: dict):
        request = message["data"]
        requests.append(request)
        if request["action"] == "stop":
            sent.set()
        else:
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
    service.stop_recording_after_successful_land()
    await asyncio.wait_for(sent.wait(), timeout=1)
    next_start = asyncio.create_task(service.start_recording_for_takeoff())
    await asyncio.sleep(0)
    assert not next_start.done()
    assert [request["action"] for request in requests] == ["start", "stop"]

    service.handle_client_message(
        recorder_id,
        {
            "type": "recording_ack",
            "data": {"request_id": requests[-1]["request_id"], "ok": True},
        },
    )
    await asyncio.wait_for(next_start, timeout=1)
    assert [request["action"] for request in requests] == ["start", "stop", "start"]


@pytest.mark.asyncio
async def test_successful_land_retries_stop_when_recorder_reconnects():
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
    service.disconnect_recorder(recorder_id)
    service.stop_recording_after_successful_land()
    assert service._stop_task is not None
    await service._stop_task

    recorder_id = service.connect_recorder(send)
    service.handle_client_message(
        recorder_id, {"type": "recorder_status", "data": {"ready": True}}
    )
    assert service._stop_task is not None
    await service._stop_task
    assert actions == ["start", "stop"]


@pytest.mark.asyncio
async def test_failed_stop_is_retried_when_same_recorder_becomes_ready():
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
                "data": {
                    "request_id": request["request_id"],
                    "ok": actions != ["start", "stop"],
                    "error": "Queue unavailable",
                },
            },
        )

    recorder_id = service.connect_recorder(send)
    service.handle_client_message(
        recorder_id, {"type": "recorder_status", "data": {"ready": True}}
    )
    await service.start_recording_for_takeoff()
    service.stop_recording_after_successful_land()
    assert service._stop_task is not None
    await service._stop_task
    assert actions == ["start", "stop"]

    service.handle_client_message(
        recorder_id, {"type": "recorder_status", "data": {"ready": True}}
    )
    assert service._stop_task is not None
    await service._stop_task
    assert actions == ["start", "stop", "stop"]
    await service.start_recording_for_takeoff()
    assert actions[-1] == "start"


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
    monkeypatch.setattr(settings, "use_mock_drone", False)

    response = test_client.post("/api/control/takeoff")

    assert response.status_code == 503
    assert "browser recorder" in response.json()["detail"]
    assert test_client.get("/api/status").json()["flying"] is False


def test_mock_takeoff_ignores_auto_recording_without_browser_recorder(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "auto_record_on_takeoff", True)
    monkeypatch.setattr(settings, "use_mock_drone", True)
    assert test_client.post("/api/control/connect").status_code == 200

    response = test_client.post("/api/control/takeoff")

    assert response.status_code == 200
    assert test_client.get("/api/status").json()["flying"] is True


def test_auto_takeoff_starts_only_after_recorder_acknowledges_start(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(settings, "auto_record_on_takeoff", True)
    assert test_client.post("/api/control/connect").status_code == 200
    monkeypatch.setattr(settings, "use_mock_drone", False)
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
    monkeypatch.setattr(settings, "use_mock_drone", False)
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
    monkeypatch.setattr(settings, "use_mock_drone", False)
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


@pytest.mark.parametrize("land_fails", [False, True])
def test_auto_recording_stops_only_after_successful_land_command(
    test_client: TestClient, monkeypatch: pytest.MonkeyPatch, land_fails: bool
):
    monkeypatch.setattr(settings, "auto_record_on_takeoff", True)
    assert test_client.post("/api/control/connect").status_code == 200
    monkeypatch.setattr(settings, "use_mock_drone", False)
    service: AutoRecordingService = app.state.auto_recording_service
    manager = app.state.drone_manager
    actions: list[str] = []
    stopped = Event()
    stop_request_id = ""
    recorder_id = ""

    async def send(message: dict):
        nonlocal stop_request_id
        request = message["data"]
        actions.append(request["action"])
        if request["action"] == "stop":
            stop_request_id = request["request_id"]
            stopped.set()
            return
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
    assert test_client.post("/api/control/takeoff").status_code == 200

    if land_fails:
        async def fail_land():
            raise RuntimeError("land failed")

        monkeypatch.setattr(manager, "land", fail_land)

    response = test_client.post("/api/control/land")

    assert response.status_code == (500 if land_fails else 200)
    if land_fails:
        assert actions == ["start"]
    else:
        assert stopped.wait(timeout=1)
        assert actions == ["start", "stop"]
        assert service._stop_task is not None
        assert not service._stop_task.done()
        assert test_client.portal is not None
        test_client.portal.call(
            service.handle_client_message,
            recorder_id,
            {
                "type": "recording_ack",
                "data": {"request_id": stop_request_id, "ok": True},
            },
        )

        async def wait_for_stop():
            assert service._stop_task is not None
            await service._stop_task

        test_client.portal.call(wait_for_stop)
