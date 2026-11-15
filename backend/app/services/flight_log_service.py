from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from app.models.telemetry import TelemetryFrame

logger = logging.getLogger(__name__)


class FlightLogService:
    """Persists flight sessions, command results, and telemetry snapshots."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self._session_id: str | None = None
        self._lock = asyncio.Lock()

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

    async def list_events(
        self, session_id: str, limit: int, offset: int
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._list_events, session_id, limit, offset)

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
                    status TEXT NOT NULL CHECK (status IN ('active', 'completed', 'interrupted'))
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
            connection.execute(
                """
                UPDATE flight_sessions
                SET status = 'interrupted', ended_at = ?
                WHERE status = 'active'
                """,
                (datetime.now(timezone.utc).isoformat(),),
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
                SELECT s.id, s.started_at, s.ended_at, s.status, COUNT(e.id) AS event_count
                FROM flight_sessions AS s
                LEFT JOIN flight_events AS e ON e.session_id = s.id
                GROUP BY s.id
                ORDER BY s.started_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]

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
