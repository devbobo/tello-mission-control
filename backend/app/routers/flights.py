import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.models.flight_log import FlightEventPage, FlightSession
from app.services.flight_log_service import (
    FlightNotFoundError,
    FlightSessionConflictError,
    FlightVideoAlreadyExistsError,
    FlightVideoTooLargeError,
)

router = APIRouter(prefix="/api/flights", tags=["flight history"])


@router.get("", response_model=list[FlightSession])
async def list_flights(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await request.app.state.flight_log_service.list_sessions(limit, offset)


@router.get("/active", response_model=FlightSession | None)
async def get_active_flight(request: Request):
    return await request.app.state.flight_log_service.get_active_session()


@router.post("/{flight_id}/next", response_model=FlightSession)
async def start_next_recording_session(flight_id: str, request: Request):
    drone_manager = request.app.state.drone_manager
    if not drone_manager.is_connected or drone_manager.is_flying:
        raise HTTPException(status_code=409, detail="Drone must be connected and grounded")
    try:
        return await request.app.state.flight_log_service.start_next_recording_session(
            flight_id
        )
    except FlightSessionConflictError as error:
        raise HTTPException(status_code=409, detail=str(error))


@router.put("/{flight_id}/video", status_code=201)
async def upload_flight_video(
    flight_id: str,
    request: Request,
    started_at: Annotated[datetime, Query()],
    duration_ms: Annotated[int, Query(ge=1)],
    recording_id: Annotated[UUID | None, Query()] = None,
):
    content_type = request.headers.get("content-type", "").split(";", maxsplit=1)[0].strip()
    if content_type != "video/webm":
        raise HTTPException(status_code=415, detail="Only WebM flight recordings are supported")

    try:
        await request.app.state.flight_log_service.store_video(
            flight_id,
            started_at,
            duration_ms,
            request.stream(),
            str(recording_id) if recording_id is not None else None,
        )
    except FlightNotFoundError:
        raise HTTPException(status_code=404, detail="Flight session not found")
    except FlightVideoAlreadyExistsError:
        raise HTTPException(status_code=409, detail="A video is already saved for this flight")
    except FlightVideoTooLargeError:
        raise HTTPException(status_code=413, detail="Flight video exceeds the configured size limit")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    return {"ok": True}


@router.get("/{flight_id}/video")
async def get_flight_video(flight_id: str, request: Request):
    video = await request.app.state.flight_log_service.get_video(flight_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Flight video not found")
    path, content_type = video
    range_header = request.headers.get("range")
    if not range_header or not range_header.startswith("bytes="):
        return FileResponse(
            path,
            media_type=content_type,
            headers={"Accept-Ranges": "bytes"},
        )

    match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
    file_size = path.stat().st_size
    if match is None:
        return Response(
            status_code=416,
            headers={"Accept-Ranges": "bytes", "Content-Range": f"bytes */{file_size}"},
        )

    start_text, end_text = match.groups()
    if not start_text:
        suffix_length = int(end_text) if end_text else 0
        if suffix_length == 0:
            return Response(
                status_code=416,
                headers={"Accept-Ranges": "bytes", "Content-Range": f"bytes */{file_size}"},
            )
        start = max(file_size - suffix_length, 0)
        end = file_size - 1
    else:
        start = int(start_text)
        end = min(int(end_text), file_size - 1) if end_text else file_size - 1

    if start >= file_size or end < start:
        return Response(
            status_code=416,
            headers={"Accept-Ranges": "bytes", "Content-Range": f"bytes */{file_size}"},
        )

    length = end - start + 1
    return StreamingResponse(
        _read_video_range(path, start, length),
        status_code=206,
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Range": f"bytes {start}-{end}/{file_size}",
        },
    )


def _read_video_range(path: Path, start: int, length: int) -> Iterator[bytes]:
    with path.open("rb") as video_file:
        video_file.seek(start)
        remaining = length
        while remaining:
            chunk = video_file.read(min(64 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


@router.get("/{flight_id}/events", response_model=FlightEventPage)
async def list_flight_events(
    flight_id: str,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    page = await request.app.state.flight_log_service.list_events(flight_id, limit, offset)
    if page is None:
        raise HTTPException(status_code=404, detail="Flight session not found")
    return {**page, "limit": limit, "offset": offset}
