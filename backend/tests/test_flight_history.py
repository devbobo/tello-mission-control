import io
import sqlite3
import time
from datetime import datetime, timedelta
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.services.flight_log_service import FlightLogService


def _create_test_webm(path: Path) -> bytes:
    with av.open(str(path), mode="w", format="webm") as output:
        stream = output.add_stream("libvpx", rate=5)
        stream.width = 320
        stream.height = 240
        stream.pix_fmt = "yuv420p"
        for index in range(5):
            image = np.full((240, 320, 3), index * 20, dtype=np.uint8)
            frame = av.VideoFrame.from_ndarray(image, format="rgb24")
            frame.pts = index
            frame.time_base = Fraction(1, 5)
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    return path.read_bytes()


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


def test_flight_video_is_transcoded_and_served_with_session(
    test_client: TestClient, tmp_path: Path
):
    assert test_client.post("/api/control/connect").status_code == 200
    session = test_client.get("/api/flights/active").json()
    assert session["video_available"] is False

    video_bytes = _create_test_webm(tmp_path / "test-recording.webm")
    response = test_client.put(
        f"/api/flights/{session['id']}/video",
        params={"started_at": session["started_at"], "duration_ms": 1500},
        headers={"content-type": "video/webm;codecs=vp8"},
        content=video_bytes,
    )
    assert response.status_code == 201

    saved_session = test_client.get("/api/flights").json()[0]
    assert saved_session["video_available"] is True
    assert saved_session["video_started_at"] == session["started_at"]
    assert saved_session["video_duration_ms"] == 1500

    history_events = test_client.get(f"/api/flights/{session['id']}/events").json()["items"]
    recording_events = {
        event["command"]: event
        for event in history_events
        if event["command"] in {"recording_start", "recording_stop"}
    }
    assert set(recording_events) == {"recording_start", "recording_stop"}
    assert all(event["event_type"] == "command" for event in recording_events.values())
    assert recording_events["recording_start"]["occurred_at"] == (
        saved_session["video_started_at"]
    )
    assert datetime.fromisoformat(recording_events["recording_stop"]["occurred_at"]) == (
        datetime.fromisoformat(recording_events["recording_start"]["occurred_at"])
        + timedelta(milliseconds=1500)
    )

    video = test_client.get(f"/api/flights/{session['id']}/video")
    assert video.status_code == 200
    assert video.headers["content-type"] == "video/mp4"
    with av.open(io.BytesIO(video.content)) as playback:
        assert playback.streams.video
        assert next(playback.decode(video=0)).width == 320

    partial_video = test_client.get(
        f"/api/flights/{session['id']}/video",
        headers={"range": "bytes=0-3"},
    )
    assert partial_video.status_code == 206
    assert partial_video.content == video.content[:4]

    duplicate = test_client.put(
        f"/api/flights/{session['id']}/video",
        params={"started_at": session["started_at"], "duration_ms": 1000},
        headers={"content-type": "video/webm"},
        content=video_bytes,
    )
    assert duplicate.status_code == 409


def test_flight_video_rejects_unknown_session_and_invalid_media(test_client: TestClient):
    started_at = "2026-11-15T00:00:00Z"
    unknown = test_client.put(
        "/api/flights/unknown/video",
        params={"started_at": started_at, "duration_ms": 1000},
        headers={"content-type": "video/webm"},
        content=b"video",
    )
    assert unknown.status_code == 404

    assert test_client.post("/api/control/connect").status_code == 200
    session = test_client.get("/api/flights/active").json()
    unsupported = test_client.put(
        f"/api/flights/{session['id']}/video",
        params={"started_at": session["started_at"], "duration_ms": 1000},
        headers={"content-type": "video/mp4"},
        content=b"video",
    )
    assert unsupported.status_code == 415


def test_flight_history_rejects_invalid_pagination(test_client: TestClient):
    assert test_client.get("/api/flights", params={"limit": 101}).status_code == 422
    assert test_client.get("/api/flights", params={"offset": -1}).status_code == 422


@pytest.mark.asyncio
async def test_existing_flight_database_schema_is_migrated(tmp_path):
    database_path = tmp_path / "flight_logs.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE flight_sessions (
                id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                status TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO flight_sessions (id, started_at, ended_at, status)
            VALUES ('legacy-flight', '2026-11-15T00:00:00+00:00',
                    '2026-11-15T00:01:00+00:00', 'completed')
            """
        )

    service = FlightLogService(database_path)
    await service.start()
    sessions = await service.list_sessions(25, 0)
    assert sessions[0]["id"] == "legacy-flight"
    assert sessions[0]["video_available"] is False
    assert sessions[0]["video_started_at"] is None
    await service.stop()


@pytest.mark.asyncio
async def test_existing_flight_videos_are_backfilled_with_recording_events(tmp_path):
    database_path = tmp_path / "flight_logs.sqlite3"
    service = FlightLogService(database_path)
    await service.start()
    await service.handle_command_log(
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
    session = await service.get_active_session()
    assert session is not None
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE flight_sessions
            SET video_path = 'existing.mp4', video_started_at = ?,
                video_duration_ms = 1500, video_content_type = 'video/mp4'
            WHERE id = ?
            """,
            (session["started_at"], session["id"]),
        )
    await service.stop()

    restarted_service = FlightLogService(database_path)
    await restarted_service.start()
    history = await restarted_service.list_events(session["id"], 100, 0)
    assert history is not None
    recording_events = {
        event["command"]: event
        for event in history["items"]
        if event["command"] in {"recording_start", "recording_stop"}
    }
    assert set(recording_events) == {"recording_start", "recording_stop"}
    assert recording_events["recording_start"]["occurred_at"] == session["started_at"]
    assert datetime.fromisoformat(recording_events["recording_stop"]["occurred_at"]) == (
        datetime.fromisoformat(session["started_at"]) + timedelta(milliseconds=1500)
    )
    await restarted_service.stop()


@pytest.mark.asyncio
async def test_legacy_webm_is_converted_on_first_playback(tmp_path):
    database_path = tmp_path / "flight_logs.sqlite3"
    service = FlightLogService(database_path)
    await service.start()
    await service.handle_command_log(
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
    session = await service.get_active_session()
    assert session is not None

    video_directory = tmp_path / "flight_videos"
    video_directory.mkdir()
    legacy_video = video_directory / "legacy.webm"
    legacy_video.write_bytes(_create_test_webm(tmp_path / "source.webm"))
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            UPDATE flight_sessions
            SET video_path = 'legacy.webm', video_started_at = ?,
                video_duration_ms = 1000, video_content_type = 'video/webm;codecs=vp8'
            WHERE id = ?
            """,
            (session["started_at"], session["id"]),
        )

    video = await service.get_video(session["id"])
    assert video is not None
    path, content_type = video
    assert content_type == "video/mp4"
    assert path.suffix == ".mp4"
    assert not legacy_video.exists()
    with av.open(str(path)) as playback:
        assert next(playback.decode(video=0)).width == 320
    await service.stop()


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
