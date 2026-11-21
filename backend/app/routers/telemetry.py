import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.telemetry import TelemetryFrame

router = APIRouter(tags=["telemetry"])
logger = logging.getLogger(__name__)


@router.websocket("/api/ws/telemetry")
async def telemetry_ws(websocket: WebSocket):
    await websocket.accept()
    telemetry_service = websocket.app.state.telemetry_service
    drone_manager = websocket.app.state.drone_manager
    auto_recording_service = websocket.app.state.auto_recording_service

    async def send_telemetry(frame: TelemetryFrame):
        await websocket.send_text(frame.model_dump_json())

    async def send_command_log(entry: dict):
        await websocket.send_text(json.dumps(entry))

    async def send_recording_request(message: dict):
        await websocket.send_text(json.dumps(message))

    recorder_id = auto_recording_service.connect_recorder(send_recording_request)
    telemetry_service.subscribe(send_telemetry)
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
        drone_manager.remove_command_log_callback(send_command_log)
        auto_recording_service.disconnect_recorder(recorder_id)
