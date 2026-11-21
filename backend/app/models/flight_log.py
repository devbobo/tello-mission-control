from typing import Any, Literal

from pydantic import BaseModel


class FlightSession(BaseModel):
    id: str
    started_at: str
    ended_at: str | None
    status: Literal["active", "completed", "interrupted"]
    event_count: int
    video_available: bool = False
    video_started_at: str | None = None
    video_duration_ms: int | None = None


class FlightEvent(BaseModel):
    id: int
    session_id: str
    event_type: Literal["command", "telemetry"]
    occurred_at: str
    command: str | None
    params: dict[str, Any]
    result: str | None
    error: str | None
    telemetry: dict[str, Any] | None


class FlightEventPage(BaseModel):
    items: list[FlightEvent]
    total: int
    limit: int
    offset: int
