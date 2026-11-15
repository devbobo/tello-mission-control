import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.telemetry import TelemetryFrame
from app.models.vision import VisionMessage

router = APIRouter(tags=["telemetry"])
logger = logging.getLogger(__name__)


@router.websocket("/api/ws/telemetry")
async def telemetry_ws(websocket: WebSocket):
    await websocket.accept()
    telemetry_service = websocket.app.state.telemetry_service
    vision_service = websocket.app.state.vision_service
    drone_manager = websocket.app.state.drone_manager

    async def send_telemetry(frame: TelemetryFrame):
        await websocket.send_text(frame.model_dump_json())

    async def send_command_log(entry: dict):
        await websocket.send_text(json.dumps(entry))

    async def send_vision(message: VisionMessage):
        await websocket.send_text(message.model_dump_json())

    telemetry_service.subscribe(send_telemetry)
    vision_service.subscribe(send_vision)
    drone_manager.add_command_log_callback(send_command_log)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    finally:
        telemetry_service.unsubscribe(send_telemetry)
        vision_service.unsubscribe(send_vision)
        drone_manager.remove_command_log_callback(send_command_log)
