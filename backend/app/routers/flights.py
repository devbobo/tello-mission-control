from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.models.flight_log import FlightEventPage, FlightSession

router = APIRouter(prefix="/api/flights", tags=["flight history"])


@router.get("", response_model=list[FlightSession])
async def list_flights(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return await request.app.state.flight_log_service.list_sessions(limit, offset)


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
