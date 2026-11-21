from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.models.commands import (
    CommandResponse,
    ConnectResponse,
    MoveRequest,
    RcControlRequest,
    RotateRequest,
)
from app.services.auto_recording_service import AutoRecordingError
from app.services.drone_manager import (
    DroneCommandBusyError,
    DroneNotConnectedError,
    DroneNotFlyingError,
)

router = APIRouter(prefix="/api/control", tags=["control"])


def _get_dm(request: Request):
    return request.app.state.drone_manager


async def _log_failure(
    request: Request,
    command: str,
    params: dict,
    error: Exception,
    occurred_at: datetime,
):
    await _get_dm(request).log_command_failure(
        command, params, str(error), occurred_at
    )


@router.post("/connect", response_model=ConnectResponse)
async def connect(request: Request):
    dm = _get_dm(request)
    command_timestamp = datetime.now(timezone.utc)
    try:
        result = await dm.connect()
        return ConnectResponse(**result)
    except Exception as e:
        await _log_failure(request, "connect", {}, e, command_timestamp)
        raise HTTPException(status_code=503, detail=f"Failed to connect: {e}")


@router.post("/disconnect", response_model=CommandResponse)
async def disconnect(request: Request):
    dm = _get_dm(request)
    command_timestamp = datetime.now(timezone.utc)
    try:
        await request.app.state.webrtc_service.close_all()
        result = await dm.disconnect()
        return CommandResponse(**result)
    except Exception as e:
        await _log_failure(request, "disconnect", {}, e, command_timestamp)
        raise HTTPException(status_code=500, detail=f"Disconnect failed: {e}")


@router.post("/takeoff", response_model=CommandResponse)
async def takeoff(request: Request):
    dm = _get_dm(request)
    auto_recording = request.app.state.auto_recording_service
    command_timestamp = datetime.now(timezone.utc)
    recording_prepared = False
    baseline_height: int | None = None
    try:
        if settings.auto_record_on_takeoff and dm.is_connected:
            await auto_recording.start_recording_for_takeoff()
            recording_prepared = True
            telemetry = await dm.get_telemetry()
            baseline_height = telemetry["height"]

        result = await dm.takeoff()
        if recording_prepared and baseline_height is not None:
            auto_recording.monitor_landing_from_height(baseline_height)
        return CommandResponse(**result)
    except AutoRecordingError as e:
        if recording_prepared:
            await auto_recording.stop_recording_after_failed_takeoff()
        await _log_failure(request, "takeoff", {}, e, command_timestamp)
        raise HTTPException(status_code=503, detail=str(e))
    except DroneNotConnectedError as e:
        if recording_prepared:
            await auto_recording.stop_recording_after_failed_takeoff()
        await _log_failure(request, "takeoff", {}, e, command_timestamp)
        raise HTTPException(status_code=409, detail="Drone is not connected")
    except Exception as e:
        if recording_prepared:
            await auto_recording.stop_recording_after_failed_takeoff()
        await _log_failure(request, "takeoff", {}, e, command_timestamp)
        raise HTTPException(status_code=500, detail=f"Takeoff failed: {e}")


@router.post("/land", response_model=CommandResponse)
async def land(request: Request):
    dm = _get_dm(request)
    command_timestamp = datetime.now(timezone.utc)
    try:
        result = await dm.land()
        return CommandResponse(**result)
    except DroneNotConnectedError as e:
        await _log_failure(request, "land", {}, e, command_timestamp)
        raise HTTPException(status_code=409, detail="Drone is not connected")
    except Exception as e:
        await _log_failure(request, "land", {}, e, command_timestamp)
        raise HTTPException(status_code=500, detail=f"Land failed: {e}")


@router.post("/emergency", response_model=CommandResponse)
async def emergency(request: Request):
    dm = _get_dm(request)
    command_timestamp = datetime.now(timezone.utc)
    try:
        result = await dm.emergency()
        return CommandResponse(**result)
    except Exception as e:
        await _log_failure(request, "emergency", {}, e, command_timestamp)
        raise HTTPException(status_code=500, detail=f"Emergency stop failed: {e}")


@router.post("/move", response_model=CommandResponse)
async def move(request: Request, body: MoveRequest):
    dm = _get_dm(request)
    command_timestamp = datetime.now(timezone.utc)
    try:
        result = await dm.move(body.direction, body.distance_cm)
        return CommandResponse(**result)
    except DroneNotConnectedError as e:
        await _log_failure(
            request,
            "move",
            {"direction": body.direction.value, "distance_cm": body.distance_cm},
            e,
            command_timestamp,
        )
        raise HTTPException(status_code=409, detail="Drone is not connected")
    except DroneNotFlyingError as e:
        await _log_failure(
            request,
            "move",
            {"direction": body.direction.value, "distance_cm": body.distance_cm},
            e,
            command_timestamp,
        )
        raise HTTPException(status_code=409, detail="Drone is not flying")
    except Exception as e:
        await _log_failure(
            request,
            "move",
            {"direction": body.direction.value, "distance_cm": body.distance_cm},
            e,
            command_timestamp,
        )
        raise HTTPException(status_code=500, detail=f"Move failed: {e}")


@router.post("/rotate", response_model=CommandResponse)
async def rotate(request: Request, body: RotateRequest):
    dm = _get_dm(request)
    command_timestamp = datetime.now(timezone.utc)
    try:
        result = await dm.rotate(body.direction, body.angle_deg)
        return CommandResponse(**result)
    except DroneNotConnectedError as e:
        await _log_failure(
            request,
            "rotate",
            {"direction": body.direction.value, "angle_deg": body.angle_deg},
            e,
            command_timestamp,
        )
        raise HTTPException(status_code=409, detail="Drone is not connected")
    except DroneNotFlyingError as e:
        await _log_failure(
            request,
            "rotate",
            {"direction": body.direction.value, "angle_deg": body.angle_deg},
            e,
            command_timestamp,
        )
        raise HTTPException(status_code=409, detail="Drone is not flying")
    except Exception as e:
        await _log_failure(
            request,
            "rotate",
            {"direction": body.direction.value, "angle_deg": body.angle_deg},
            e,
            command_timestamp,
        )
        raise HTTPException(status_code=500, detail=f"Rotate failed: {e}")


@router.post("/rc", response_model=CommandResponse)
async def rc_control(request: Request, body: RcControlRequest):
    dm = _get_dm(request)
    params = body.model_dump()
    command_timestamp = datetime.now(timezone.utc)
    try:
        result = await dm.send_rc_control(body.lr, body.fb, body.ud, body.yaw)
        return CommandResponse(**result)
    except DroneCommandBusyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except DroneNotConnectedError as e:
        await _log_failure(request, "rc_control", params, e, command_timestamp)
        raise HTTPException(status_code=409, detail="Drone is not connected")
    except DroneNotFlyingError as e:
        await _log_failure(request, "rc_control", params, e, command_timestamp)
        raise HTTPException(status_code=409, detail="Drone is not flying")
    except Exception as e:
        await _log_failure(request, "rc_control", params, e, command_timestamp)
        raise HTTPException(status_code=500, detail=f"RC control failed: {e}")
