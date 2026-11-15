from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings

from app.models.video import WebRTCIceServer


class Settings(BaseSettings):
    # Drone connection
    tello_host: str = "192.168.10.1"
    tello_retry_count: int = 3

    # Server
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # MCP server
    mcp_api_url: str = "http://127.0.0.1:8000"
    mcp_request_timeout: float = 10.0

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # Telemetry
    telemetry_poll_hz: float = 4.0

    # Flight history
    flight_log_db_path: Path = Path("data/flight_logs.sqlite3")

    # Video
    video_fps: int = 30
    video_jpeg_quality: int = 70
    webrtc_public_host: str | None = None
    webrtc_ice_servers: list[WebRTCIceServer] = Field(default_factory=list)

    # Computer vision
    vision_model_path: Path | None = None
    vision_device: Literal["auto", "cpu", "cuda", "mps"] = "auto"
    vision_inference_hz: float = Field(default=5.0, gt=0, le=30)
    vision_confidence_threshold: float = Field(default=0.25, ge=0, le=1)
    vision_class_names: list[str] = Field(default_factory=list)
    vision_model_format: Literal["auto", "yolov8", "yolov10"] = "auto"

    # Mock mode (for development/testing without a physical drone)
    use_mock_drone: bool = False

    model_config = {"env_prefix": "TELLO_"}


settings = Settings()
