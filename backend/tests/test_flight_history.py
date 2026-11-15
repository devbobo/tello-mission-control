import time

import pytest
from fastapi.testclient import TestClient

from app.services.flight_log_service import FlightLogService


def test_flight_history_persists_commands_and_telemetry(test_client: TestClient):
    assert test_client.post("/api/control/connect").status_code == 200
    failed_move = test_client.post(
        "/api/control/move",
        json={"direction": "forward", "distance_cm": 100},
    )
    assert failed_move.status_code == 409
    assert test_client.post("/api/control/takeoff").status_code == 200
    assert test_client.post(
        "/api/control/rotate",
        json={"direction": "cw", "angle_deg": 90},
    ).status_code == 200

    time.sleep(0.3)
    sessions = test_client.get("/api/flights").json()
    assert len(sessions) == 1
    session = sessions[0]
    assert session["status"] == "active"

    response = test_client.get(f"/api/flights/{session['id']}/events")
    assert response.status_code == 200
    events = response.json()["items"]

    telemetry = next(event for event in events if event["event_type"] == "telemetry")
    assert telemetry["telemetry"]["battery"] == 85
    assert telemetry["telemetry"]["height"] == 50
    commands = [event for event in events if event["event_type"] == "command"]
    assert [event["command"] for event in commands[:2]] == ["connect", "move"]
    assert commands[1]["result"] == "error"
    assert commands[1]["params"] == {"direction": "forward", "distance_cm": 100}
    assert any(event["command"] == "takeoff" and event["result"] == "ok" for event in commands)
    assert any(event["command"] == "rotate" for event in commands)

    assert test_client.post("/api/control/disconnect").status_code == 200
    completed = test_client.get(f"/api/flights/{session['id']}/events").json()["items"]
    disconnect = [event for event in completed if event["command"] == "disconnect"]
    assert len(disconnect) == 1
    assert any(event["command"] == "land" for event in completed)
    assert test_client.get("/api/flights").json()[0]["status"] == "completed"


def test_flight_history_events_are_paginated(test_client: TestClient):
    test_client.post("/api/control/connect")
    test_client.post("/api/control/takeoff")
    test_client.post("/api/control/land")

    session = test_client.get("/api/flights").json()[0]
    first_page = test_client.get(
        f"/api/flights/{session['id']}/events", params={"limit": 2, "offset": 0}
    ).json()
    second_page = test_client.get(
        f"/api/flights/{session['id']}/events", params={"limit": 2, "offset": 2}
    ).json()

    assert first_page["total"] == session["event_count"]
    assert len(first_page["items"]) == 2
    assert second_page["items"][0]["id"] > first_page["items"][-1]["id"]


def test_flight_history_returns_not_found_for_unknown_session(test_client: TestClient):
    response = test_client.get("/api/flights/unknown/events")
    assert response.status_code == 404


def test_flight_history_rejects_invalid_pagination(test_client: TestClient):
    assert test_client.get("/api/flights", params={"limit": 101}).status_code == 422
    assert test_client.get("/api/flights", params={"offset": -1}).status_code == 422


@pytest.mark.asyncio
async def test_active_sessions_are_marked_interrupted_after_restart(tmp_path):
    database_path = tmp_path / "flight_logs.sqlite3"
    first_service = FlightLogService(database_path)
    await first_service.start()
    await first_service.handle_command_log(
        {
            "type": "command_log",
            "data": {
                "command": "connect",
                "params": {},
                "result": "ok",
                "timestamp": "2026-11-15T00:00:00+00:00",
            },
        }
    )
    await first_service.stop()

    restarted_service = FlightLogService(database_path)
    await restarted_service.start()
    sessions = await restarted_service.list_sessions(25, 0)

    assert sessions[0]["status"] == "interrupted"
    assert sessions[0]["ended_at"] is not None
    await restarted_service.stop()
