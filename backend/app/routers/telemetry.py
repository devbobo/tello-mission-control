import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.markers import MarkerMessage
from app.models.odometry import OdometryMessage
from app.models.telemetry import TelemetryFrame
from app.models.vision import VisionMessage

router = APIRouter(tags=["telemetry"])
logger = logging.getLogger(__name__)


@router.websocket("/api/ws/telemetry")
async def telemetry_ws(websocket: WebSocket):
    await websocket.accept()
    telemetry_service = websocket.app.state.telemetry_service
    vision_service = websocket.app.state.vision_service
    odometry_service = websocket.app.state.odometry_service
    marker_service = websocket.app.state.marker_service
    drone_manager = websocket.app.state.drone_manager
    auto_recording_service = websocket.app.state.auto_recording_service

    async def send_telemetry(frame: TelemetryFrame):
        await websocket.send_text(frame.model_dump_json())

    async def send_command_log(entry: dict):
        await websocket.send_text(json.dumps(entry))

    async def send_vision(message: VisionMessage):
        await websocket.send_text(message.model_dump_json())

    async def send_odometry(message: OdometryMessage):
        await websocket.send_text(message.model_dump_json())

    async def send_markers(message: MarkerMessage):
        await websocket.send_text(message.model_dump_json())

    async def send_recording_request(message: dict):
        await websocket.send_text(json.dumps(message))

    recorder_id = auto_recording_service.connect_recorder(send_recording_request)
    telemetry_service.subscribe(send_telemetry)
    vision_service.subscribe(send_vision)
    odometry_service.subscribe(send_odometry)
    marker_service.subscribe(send_markers)
    drone_manager.add_command_log_callback(send_command_log)

    try:
        while True:
            message_text = await websocket.receive_text()
            try:
                message = json.loads(message_text)
            except json.JSONDecodeError:
                logger.warning("Ignoring malformed telemetry WebSocket message")
                continue
            if isinstance(message, dict):
                auto_recording_service.handle_client_message(recorder_id, message)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    finally:
        telemetry_service.unsubscribe(send_telemetry)
        vision_service.unsubscribe(send_vision)
        odometry_service.unsubscribe(send_odometry)
        marker_service.unsubscribe(send_markers)
        drone_manager.remove_command_log_callback(send_command_log)
        auto_recording_service.disconnect_recorder(recorder_id)
