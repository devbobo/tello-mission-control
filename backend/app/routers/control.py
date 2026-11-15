from fastapi import APIRouter, HTTPException, Request

from app.models.commands import (
    CommandResponse,
    ConnectResponse,
    MoveRequest,
    RotateRequest,
)
from app.services.drone_manager import DroneNotConnectedError, DroneNotFlyingError

router = APIRouter(prefix="/api/control", tags=["control"])


def _get_dm(request: Request):
    return request.app.state.drone_manager


async def _log_failure(request: Request, command: str, params: dict, error: Exception):
    await _get_dm(request).log_command_failure(command, params, str(error))


@router.post("/connect", response_model=ConnectResponse)
async def connect(request: Request):
    dm = _get_dm(request)
    try:
        result = await dm.connect()
        return ConnectResponse(**result)
    except Exception as e:
        await _log_failure(request, "connect", {}, e)
        raise HTTPException(status_code=503, detail=f"Failed to connect: {e}")


@router.post("/disconnect", response_model=CommandResponse)
async def disconnect(request: Request):
    dm = _get_dm(request)
    try:
        result = await dm.disconnect()
        return CommandResponse(**result)
    except Exception as e:
        await _log_failure(request, "disconnect", {}, e)
        raise HTTPException(status_code=500, detail=f"Disconnect failed: {e}")


@router.post("/takeoff", response_model=CommandResponse)
async def takeoff(request: Request):
    dm = _get_dm(request)
    try:
        result = await dm.takeoff()
        return CommandResponse(**result)
    except DroneNotConnectedError as e:
        await _log_failure(request, "takeoff", {}, e)
        raise HTTPException(status_code=409, detail="Drone is not connected")
    except Exception as e:
        await _log_failure(request, "takeoff", {}, e)
        raise HTTPException(status_code=500, detail=f"Takeoff failed: {e}")


@router.post("/land", response_model=CommandResponse)
async def land(request: Request):
    dm = _get_dm(request)
    try:
        result = await dm.land()
        return CommandResponse(**result)
    except DroneNotConnectedError as e:
        await _log_failure(request, "land", {}, e)
        raise HTTPException(status_code=409, detail="Drone is not connected")
    except Exception as e:
        await _log_failure(request, "land", {}, e)
        raise HTTPException(status_code=500, detail=f"Land failed: {e}")


@router.post("/emergency", response_model=CommandResponse)
async def emergency(request: Request):
    dm = _get_dm(request)
    try:
        result = await dm.emergency()
        return CommandResponse(**result)
    except Exception as e:
        await _log_failure(request, "emergency", {}, e)
        raise HTTPException(status_code=500, detail=f"Emergency stop failed: {e}")


@router.post("/move", response_model=CommandResponse)
async def move(request: Request, body: MoveRequest):
    dm = _get_dm(request)
    try:
        result = await dm.move(body.direction, body.distance_cm)
        return CommandResponse(**result)
    except DroneNotConnectedError as e:
        await _log_failure(
            request,
            "move",
            {"direction": body.direction.value, "distance_cm": body.distance_cm},
            e,
        )
        raise HTTPException(status_code=409, detail="Drone is not connected")
    except DroneNotFlyingError as e:
        await _log_failure(
            request,
            "move",
            {"direction": body.direction.value, "distance_cm": body.distance_cm},
            e,
        )
        raise HTTPException(status_code=409, detail="Drone is not flying")
    except Exception as e:
        await _log_failure(
            request,
            "move",
            {"direction": body.direction.value, "distance_cm": body.distance_cm},
            e,
        )
        raise HTTPException(status_code=500, detail=f"Move failed: {e}")


@router.post("/rotate", response_model=CommandResponse)
async def rotate(request: Request, body: RotateRequest):
    dm = _get_dm(request)
    try:
        result = await dm.rotate(body.direction, body.angle_deg)
        return CommandResponse(**result)
    except DroneNotConnectedError as e:
        await _log_failure(
            request,
            "rotate",
            {"direction": body.direction.value, "angle_deg": body.angle_deg},
            e,
        )
        raise HTTPException(status_code=409, detail="Drone is not connected")
    except DroneNotFlyingError as e:
        await _log_failure(
            request,
            "rotate",
            {"direction": body.direction.value, "angle_deg": body.angle_deg},
            e,
        )
        raise HTTPException(status_code=409, detail="Drone is not flying")
    except Exception as e:
        await _log_failure(
            request,
            "rotate",
            {"direction": body.direction.value, "angle_deg": body.angle_deg},
            e,
        )
        raise HTTPException(status_code=500, detail=f"Rotate failed: {e}")
