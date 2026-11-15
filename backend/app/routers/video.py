import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlsplit

import cv2
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.config import settings
from app.models.commands import CommandResponse
from app.models.video import WebRTCAnswer, WebRTCOffer
from app.services.drone_manager import DroneNotConnectedError

router = APIRouter(prefix="/api/video", tags=["video"])
logger = logging.getLogger(__name__)


def _local_address_for_drone(remote_host: str) -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route_socket:
            # UDP connect selects the route without sending a datagram.
            route_socket.connect((remote_host, 8889))
            local_host = route_socket.getsockname()[0]
    except OSError as error:
        logger.warning(
            "Unable to determine local WebRTC address for Tello host %s: %s",
            remote_host,
            error,
        )
        return None

    address = ipaddress.ip_address(local_host)
    if address.is_loopback or address.is_unspecified:
        return None
    return local_host


def _is_loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


async def _log_stream_failure(drone_manager, command: str, error: Exception) -> None:
    await drone_manager.log_command_failure(command, {}, str(error))


@router.get("/webrtc/config")
async def video_webrtc_config() -> dict[str, list[dict]]:
    """Return ICE servers needed by both browser and backend peers."""
    return {
        "iceServers": [
            server.model_dump(exclude_none=True)
            for server in settings.webrtc_ice_servers
        ]
    }


@router.post("/webrtc/offer", response_model=WebRTCAnswer)
async def video_webrtc_offer(request: Request, body: WebRTCOffer):
    """Negotiate a WebRTC video peer using a browser-generated SDP offer."""
    dm = request.app.state.drone_manager
    service = request.app.state.webrtc_service
    origin = request.headers.get("origin")
    try:
        origin_host = urlsplit(origin).hostname if origin else None
    except ValueError:
        origin_host = None
    public_host = settings.webrtc_public_host or origin_host or request.url.hostname
    if not public_host:
        raise HTTPException(status_code=400, detail="Unable to determine WebRTC host")
    if (
        not settings.webrtc_public_host
        and not settings.use_mock_drone
        and _is_loopback_host(public_host)
    ):
        public_host = _local_address_for_drone(settings.tello_host) or public_host

    try:
        answer = await service.create_answer(body.sdp, public_host)
        return WebRTCAnswer(**answer)
    except DroneNotConnectedError as e:
        await _log_stream_failure(dm, "webrtc_offer", e)
        raise HTTPException(status_code=409, detail="Drone is not connected")
    except ValueError as e:
        await _log_stream_failure(dm, "webrtc_offer", e)
        raise HTTPException(status_code=400, detail=f"Invalid WebRTC offer: {e}")
    except Exception as e:
        await _log_stream_failure(dm, "webrtc_offer", e)
        raise HTTPException(status_code=500, detail=f"WebRTC negotiation failed: {e}")


@router.delete("/webrtc/{peer_id}", status_code=204)
async def close_webrtc_peer(request: Request, peer_id: str):
    """Close a browser's WebRTC peer connection."""
    await request.app.state.webrtc_service.close_peer(peer_id)
    return Response(status_code=204)


@router.post("/stream/start", response_model=CommandResponse)
async def stream_start(request: Request):
    """Explicitly start the video stream."""
    dm = request.app.state.drone_manager
    try:
        result = await dm.stream_on()
        return CommandResponse(**result)
    except DroneNotConnectedError as e:
        await _log_stream_failure(dm, "stream_on", e)
        raise HTTPException(status_code=409, detail="Drone is not connected")
    except Exception as e:
        await _log_stream_failure(dm, "stream_on", e)
        raise HTTPException(status_code=500, detail=f"Failed to start stream: {e}")


@router.post("/stream/stop", response_model=CommandResponse)
async def stream_stop(request: Request):
    """Close video peers and explicitly stop the video stream."""
    dm = request.app.state.drone_manager
    try:
        await request.app.state.webrtc_service.close_all()
        result = await dm.stream_off()
        return CommandResponse(**result)
    except DroneNotConnectedError as e:
        await _log_stream_failure(dm, "stream_off", e)
        raise HTTPException(status_code=409, detail="Drone is not connected")
    except Exception as e:
        await _log_stream_failure(dm, "stream_off", e)
        raise HTTPException(status_code=500, detail=f"Failed to stop stream: {e}")


@router.post("/snapshot")
async def snapshot(request: Request):
    """Capture a single frame as JPEG."""
    dm = request.app.state.drone_manager

    if not dm.is_connected:
        raise HTTPException(status_code=409, detail="Drone is not connected")

    if not dm.is_streaming:
        try:
            await dm.stream_on()
        except Exception as e:
            await _log_stream_failure(dm, "stream_on", e)
            raise HTTPException(status_code=500, detail=f"Failed to start stream: {e}")

    frame = dm.get_frame()
    if frame is None:
        await asyncio.sleep(0.01)
        frame = dm.get_frame()
    if frame is None:
        raise HTTPException(status_code=503, detail="No frame available")

    _, jpeg = cv2.imencode(".jpg", frame)
    return Response(
        content=jpeg.tobytes(),
        media_type="image/jpeg",
        headers={"Content-Disposition": "attachment; filename=tello_snapshot.jpg"},
    )
