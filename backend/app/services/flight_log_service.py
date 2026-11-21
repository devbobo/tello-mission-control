from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any, AsyncIterator, Generator

import av

from app.config import settings
from app.models.telemetry import TelemetryFrame

logger = logging.getLogger(__name__)


class FlightNotFoundError(Exception):
    pass


class FlightVideoAlreadyExistsError(Exception):
    pass


class FlightVideoTooLargeError(Exception):
    pass


class FlightSessionConflictError(Exception):
    pass


class FlightLogService:
    """Persists flight sessions, command results, and telemetry snapshots."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._video_directory = database_path.parent / "flight_videos"
        self._session_id: str | None = None
        self._lock = asyncio.Lock()
        self._video_lock = asyncio.Lock()

    async def start(self) -> None:
        await asyncio.to_thread(self._initialize_database)

    async def stop(self) -> None:
        async with self._lock:
            self._session_id = None

    async def handle_command_log(self, entry: dict[str, Any]) -> None:
        data = entry.get("data", {})
        command = data.get("command")
        if not isinstance(command, str):
            logger.warning("Ignoring command log without a command name")
            return

        timestamp = data.get("timestamp") or datetime.now(timezone.utc).isoformat()
        params = data.get("params") or {}
        result = data.get("result", "error")
        error = data.get("error")

        async with self._lock:
            if command == "connect" and result == "ok" and self._session_id is None:
                session_id = str(uuid.uuid4())
                await asyncio.to_thread(
                    self._create_session_and_event,
                    session_id,
                    timestamp,
                    command,
                    params,
                    result,
                    error,
                )
                self._session_id = session_id
                return

            if self._session_id is None:
                return

            await asyncio.to_thread(
                self._insert_event,
                self._session_id,
                "command",
                timestamp,
                command,
                params,
                result,
                error,
                None,
            )

            if command == "disconnect":
                await asyncio.to_thread(self._finish_session, self._session_id, timestamp)
                self._session_id = None

    async def record_telemetry(self, frame: TelemetryFrame) -> None:
        async with self._lock:
            if self._session_id is None:
                return
            await asyncio.to_thread(
                self._insert_event,
                self._session_id,
                "telemetry",
                frame.timestamp.isoformat(),
                None,
                {},
                None,
                None,
                frame.model_dump(mode="json")["data"],
            )

    async def record_command_failure(
        self, command: str, params: dict[str, Any], error: str
    ) -> None:
        await self.handle_command_log(
            {
                "type": "command_log",
                "data": {
                    "command": command,
                    "params": params,
                    "result": "error",
                    "error": error,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            }
        )

    async def list_sessions(self, limit: int, offset: int) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_sessions, limit, offset)

    async def get_active_session(self) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_active_session)

    async def start_next_recording_session(self, session_id: str) -> dict[str, Any]:
        async with self._lock:
            if self._session_id != session_id:
                raise FlightSessionConflictError("Flight session is no longer active")
            next_id = str(uuid.uuid4())
            timestamp = datetime.now(timezone.utc).isoformat()
            await asyncio.to_thread(
                self._rollover_recorded_session, session_id, next_id, timestamp
            )
            self._session_id = next_id
            session = await asyncio.to_thread(self._get_active_session)
            if session is None:
                raise RuntimeError("New flight session was not found")
            return session

    async def list_events(
        self, session_id: str, limit: int, offset: int
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._list_events, session_id, limit, offset)

    async def store_video(
        self,
        session_id: str,
        started_at: datetime,
        duration_ms: int,
        chunks: AsyncIterator[bytes],
        recording_id: str | None = None,
    ) -> None:
        session = await asyncio.to_thread(self._get_session_video_metadata, session_id)
        if session is None:
            raise FlightNotFoundError(session_id)
        if session["video_path"] is not None:
            if (
                recording_id is not None
                and session["video_recording_id"] == recording_id
                and (self._video_directory / session["video_path"]).is_file()
            ):
                return
            raise FlightVideoAlreadyExistsError(session_id)

        started_at = _as_utc(started_at)
        session_started_at = _as_utc(datetime.fromisoformat(session["started_at"]))
        if started_at < session_started_at:
            raise ValueError("Video recording must start during its flight session")
        if session["ended_at"] is not None:
            session_ended_at = _as_utc(datetime.fromisoformat(session["ended_at"]))
            if started_at > session_ended_at:
                raise ValueError("Video recording must start during its flight session")

        await asyncio.to_thread(self._video_directory.mkdir, parents=True, exist_ok=True)
        temporary_path = self._video_directory / f".{uuid.uuid4().hex}.webm"
        transcoded_path = self._video_directory / f".{uuid.uuid4().hex}.mp4"
        size = 0
        try:
            async for chunk in chunks:
                if not chunk:
                    continue
                size += len(chunk)
                if size > settings.flight_video_max_bytes:
                    raise FlightVideoTooLargeError(str(settings.flight_video_max_bytes))
                await asyncio.to_thread(_append_file, temporary_path, chunk)

            if size == 0:
                raise ValueError("Uploaded video is empty")

            await asyncio.to_thread(
                _transcode_webm_to_mp4, temporary_path, transcoded_path
            )
            if transcoded_path.stat().st_size > settings.flight_video_max_bytes:
                raise FlightVideoTooLargeError(str(settings.flight_video_max_bytes))

            async with self._lock:
                await asyncio.to_thread(
                    self._attach_video,
                    session_id,
                    transcoded_path,
                    started_at.isoformat(),
                    duration_ms,
                    recording_id,
                )
        finally:
            await asyncio.to_thread(temporary_path.unlink, missing_ok=True)
            await asyncio.to_thread(transcoded_path.unlink, missing_ok=True)

    async def get_video(self, session_id: str) -> tuple[Path, str] | None:
        video = await asyncio.to_thread(self._get_video, session_id)
        if video is None or not _is_webm(video[1]):
            return video

        async with self._video_lock:
            video = await asyncio.to_thread(self._get_video, session_id)
            if video is not None and _is_webm(video[1]):
                source_path, _ = video
                transcoded_path = self._video_directory / f".{uuid.uuid4().hex}.mp4"
                try:
                    await asyncio.to_thread(
                        _transcode_webm_to_mp4, source_path, transcoded_path
                    )
                    if transcoded_path.stat().st_size > settings.flight_video_max_bytes:
                        raise FlightVideoTooLargeError(
                            str(settings.flight_video_max_bytes)
                        )
                    await asyncio.to_thread(
                        self._replace_legacy_video,
                        session_id,
                        source_path,
                        transcoded_path,
                    )
                finally:
                    await asyncio.to_thread(transcoded_path.unlink, missing_ok=True)

        return await asyncio.to_thread(self._get_video, session_id)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize_database(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS flight_sessions (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'interrupted')),
                    video_path TEXT,
                    video_started_at TEXT,
                    video_duration_ms INTEGER,
                    video_content_type TEXT,
                    video_recording_id TEXT
                );
                CREATE INDEX IF NOT EXISTS flight_sessions_started_at
                    ON flight_sessions(started_at DESC);
                CREATE TABLE IF NOT EXISTS flight_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES flight_sessions(id),
                    event_type TEXT NOT NULL CHECK (event_type IN ('command', 'telemetry')),
                    occurred_at TEXT NOT NULL,
                    command TEXT,
                    params_json TEXT NOT NULL DEFAULT '{}',
                    result TEXT,
                    error TEXT,
                    telemetry_json TEXT
                );
                CREATE INDEX IF NOT EXISTS flight_events_session_time
                    ON flight_events(session_id, occurred_at, id);
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(flight_sessions)")
            }
            for name, column_type in (
                ("video_path", "TEXT"),
                ("video_started_at", "TEXT"),
                ("video_duration_ms", "INTEGER"),
                ("video_content_type", "TEXT"),
                ("video_recording_id", "TEXT"),
            ):
                if name not in columns:
                    connection.execute(
                        f"ALTER TABLE flight_sessions ADD COLUMN {name} {column_type}"
                    )
            connection.execute(
                """
                UPDATE flight_sessions
                SET status = 'interrupted', ended_at = ?
                WHERE status = 'active'
                """,
                (datetime.now(timezone.utc).isoformat(),),
            )
            recorded_sessions = connection.execute(
                """
                SELECT id, video_started_at, video_duration_ms
                FROM flight_sessions
                WHERE video_path IS NOT NULL
                  AND video_started_at IS NOT NULL
                  AND video_duration_ms IS NOT NULL
                """
            ).fetchall()
            for session in recorded_sessions:
                self._insert_recording_events_on_connection(
                    connection,
                    session["id"],
                    session["video_started_at"],
                    session["video_duration_ms"],
                )

    def _create_session_and_event(
        self,
        session_id: str,
        timestamp: str,
        command: str,
        params: dict[str, Any],
        result: str,
        error: str | None,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO flight_sessions (id, started_at, status)
                VALUES (?, ?, 'active')
                """,
                (session_id, timestamp),
            )
            self._insert_event_on_connection(
                connection, session_id, "command", timestamp, command, params, result, error, None
            )

    def _rollover_recorded_session(
        self, session_id: str, next_id: str, timestamp: str
    ) -> None:
        with self._connection() as connection:
            result = connection.execute(
                """
                UPDATE flight_sessions SET status = 'completed', ended_at = ?
                WHERE id = ? AND status = 'active'
                """,
                (timestamp, session_id),
            )
            if result.rowcount != 1:
                raise FlightSessionConflictError("Flight session is no longer active")
            connection.execute(
                "INSERT INTO flight_sessions (id, started_at, status) VALUES (?, ?, 'active')",
                (next_id, timestamp),
            )

    def _insert_event(
        self,
        session_id: str,
        event_type: str,
        timestamp: str,
        command: str | None,
        params: dict[str, Any],
        result: str | None,
        error: str | None,
        telemetry: dict[str, Any] | None,
    ) -> None:
        with self._connection() as connection:
            self._insert_event_on_connection(
                connection, session_id, event_type, timestamp, command, params, result, error, telemetry
            )

    @staticmethod
    def _insert_event_on_connection(
        connection: sqlite3.Connection,
        session_id: str,
        event_type: str,
        timestamp: str,
        command: str | None,
        params: dict[str, Any],
        result: str | None,
        error: str | None,
        telemetry: dict[str, Any] | None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO flight_events
                (session_id, event_type, occurred_at, command, params_json, result, error, telemetry_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                event_type,
                timestamp,
                command,
                json.dumps(params),
                result,
                error,
                json.dumps(telemetry) if telemetry is not None else None,
            ),
        )

    @staticmethod
    def _insert_recording_events_on_connection(
        connection: sqlite3.Connection,
        session_id: str,
        started_at: str,
        duration_ms: int,
    ) -> None:
        start_time = _as_utc(datetime.fromisoformat(started_at))
        recording_events = (
            ("recording_start", start_time),
            ("recording_stop", start_time + timedelta(milliseconds=duration_ms)),
        )
        for command, timestamp in recording_events:
            exists = connection.execute(
                """
                SELECT 1
                FROM flight_events
                WHERE session_id = ? AND event_type = 'command' AND command = ?
                LIMIT 1
                """,
                (session_id, command),
            ).fetchone()
            if exists is None:
                FlightLogService._insert_event_on_connection(
                    connection,
                    session_id,
                    "command",
                    timestamp.isoformat(),
                    command,
                    {},
                    "ok",
                    None,
                    None,
                )

    def _finish_session(self, session_id: str, timestamp: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE flight_sessions
                SET status = 'completed', ended_at = ?
                WHERE id = ?
                """,
                (timestamp, session_id),
            )

    def _list_sessions(self, limit: int, offset: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT s.id, s.started_at, s.ended_at, s.status, COUNT(e.id) AS event_count,
                       s.video_path, s.video_started_at, s.video_duration_ms
                FROM flight_sessions AS s
                LEFT JOIN flight_events AS e ON e.session_id = s.id
                GROUP BY s.id
                ORDER BY s.started_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [self._session_response(dict(row)) for row in rows]

    def _get_active_session(self) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT s.id, s.started_at, s.ended_at, s.status, COUNT(e.id) AS event_count,
                       s.video_path, s.video_started_at, s.video_duration_ms
                FROM flight_sessions AS s
                LEFT JOIN flight_events AS e ON e.session_id = s.id
                WHERE s.status = 'active'
                GROUP BY s.id
                ORDER BY s.started_at DESC
                LIMIT 1
                """
            ).fetchone()
        return self._session_response(dict(row)) if row is not None else None

    def _session_response(self, session: dict[str, Any]) -> dict[str, Any]:
        video_path = session.pop("video_path")
        session["video_available"] = (
            video_path is not None and (self._video_directory / video_path).is_file()
        )
        return session

    def _get_session_video_metadata(self, session_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT started_at, ended_at, video_path, video_recording_id
                FROM flight_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        return dict(row) if row is not None else None

    def _attach_video(
        self,
        session_id: str,
        temporary_path: Path,
        started_at: str,
        duration_ms: int,
        recording_id: str | None,
    ) -> None:
        stored_name = f"{uuid.uuid4().hex}.mp4"
        stored_path = self._video_directory / stored_name
        with self._connection() as connection:
            row = connection.execute(
                "SELECT video_path, video_recording_id FROM flight_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise FlightNotFoundError(session_id)
            if row["video_path"] is not None:
                if (
                    recording_id is not None
                    and row["video_recording_id"] == recording_id
                    and (self._video_directory / row["video_path"]).is_file()
                ):
                    return
                raise FlightVideoAlreadyExistsError(session_id)

            os.replace(temporary_path, stored_path)
            try:
                connection.execute(
                    """
                    UPDATE flight_sessions
                    SET video_path = ?, video_started_at = ?, video_duration_ms = ?,
                        video_content_type = ?, video_recording_id = ?
                    WHERE id = ?
                    """,
                    (stored_name, started_at, duration_ms, "video/mp4", recording_id, session_id),
                )
                self._insert_recording_events_on_connection(
                    connection, session_id, started_at, duration_ms
                )
            except Exception:
                stored_path.unlink(missing_ok=True)
                raise

    def _replace_legacy_video(
        self, session_id: str, source_path: Path, transcoded_path: Path
    ) -> None:
        stored_name = f"{uuid.uuid4().hex}.mp4"
        stored_path = self._video_directory / stored_name
        with self._connection() as connection:
            row = connection.execute(
                "SELECT video_path FROM flight_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise FlightNotFoundError(session_id)
            if row["video_path"] != source_path.name:
                return

            os.replace(transcoded_path, stored_path)
            try:
                connection.execute(
                    """
                    UPDATE flight_sessions
                    SET video_path = ?, video_content_type = 'video/mp4'
                    WHERE id = ?
                    """,
                    (stored_name, session_id),
                )
            except Exception:
                stored_path.unlink(missing_ok=True)
                raise
        source_path.unlink(missing_ok=True)

    def _get_video(self, session_id: str) -> tuple[Path, str] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT video_path, video_content_type
                FROM flight_sessions
                WHERE id = ?
                """,
                (session_id,),
            ).fetchone()
        if row is None or row["video_path"] is None:
            return None
        path = self._video_directory / row["video_path"]
        if not path.is_file():
            return None
        return path, row["video_content_type"] or "video/webm"

    def _list_events(
        self, session_id: str, limit: int, offset: int
    ) -> dict[str, Any] | None:
        with self._connect() as connection:
            session = connection.execute(
                "SELECT id FROM flight_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if session is None:
                return None

            total = connection.execute(
                "SELECT COUNT(*) FROM flight_events WHERE session_id = ?", (session_id,)
            ).fetchone()[0]
            rows = connection.execute(
                """
                SELECT id, session_id, event_type, occurred_at, command, params_json,
                       result, error, telemetry_json
                FROM flight_events
                WHERE session_id = ?
                ORDER BY occurred_at, id
                LIMIT ? OFFSET ?
                """,
                (session_id, limit, offset),
            ).fetchall()

        events = []
        for row in rows:
            event = dict(row)
            event["params"] = json.loads(event.pop("params_json"))
            telemetry_json = event.pop("telemetry_json")
            event["telemetry"] = json.loads(telemetry_json) if telemetry_json else None
            events.append(event)
        return {"items": events, "total": total}


def _append_file(path: Path, chunk: bytes) -> None:
    with path.open("ab") as video_file:
        video_file.write(chunk)


def _transcode_webm_to_mp4(source_path: Path, destination_path: Path) -> None:
    with av.open(str(source_path), mode="r") as source:
        source_stream = next(
            (stream for stream in source.streams if stream.type == "video"), None
        )
        if source_stream is None:
            raise ValueError("Flight recording contains no video stream")

        frame_rate = source_stream.average_rate
        if frame_rate is None or frame_rate <= 0:
            frame_rate = settings.video_fps
        frame_rate = Fraction(frame_rate)
        frame_time_base = Fraction(1, 90_000)

        with av.open(
            str(destination_path),
            mode="w",
            format="mp4",
            options={"movflags": "+faststart"},
        ) as output:
            output_stream = output.add_stream("libx264", rate=frame_rate)
            output_stream.width = source_stream.width
            output_stream.height = source_stream.height
            output_stream.pix_fmt = "yuv420p"
            output_stream.bit_rate = 2_000_000
            output_stream.codec_context.time_base = frame_time_base

            frame_count = 0
            previous_pts: int | None = None
            for frame in source.decode(source_stream):
                if frame.pts is not None and frame.time_base is not None:
                    pts = round(frame.pts * frame.time_base / frame_time_base)
                elif previous_pts is None:
                    pts = 0
                else:
                    pts = previous_pts + round(1 / frame_rate / frame_time_base)
                if previous_pts is not None:
                    pts = max(pts, previous_pts + 1)
                previous_pts = pts
                frame.pts = pts
                frame.time_base = frame_time_base
                frame = frame.reformat(format="yuv420p")
                for packet in output_stream.encode(frame):
                    output.mux(packet)
                frame_count += 1

            if frame_count == 0:
                raise ValueError("Flight recording contains no decodable video frames")

            for packet in output_stream.encode():
                output.mux(packet)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Video timestamp must include a timezone")
    return value.astimezone(timezone.utc)


def _is_webm(content_type: str) -> bool:
    return content_type.split(";", maxsplit=1)[0].strip().lower() == "video/webm"
