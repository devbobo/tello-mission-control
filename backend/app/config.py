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
    flight_video_max_bytes: int = Field(default=524_288_000, gt=0)
    auto_record_on_takeoff: bool = False
    auto_record_landing_speed_threshold_cm_s: float = Field(default=0, ge=0)
    auto_record_landing_confirmation_samples: int = Field(default=8, ge=1)

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
    vision_odometry_hz: float = Field(default=5.0, gt=0, le=30)
    vision_marker_hz: float = Field(default=5.0, gt=0, le=30)
    vision_aruco_dictionary: str = "DICT_4X4_50"

    # Mock mode (for development/testing without a physical drone)
    use_mock_drone: bool = False

    model_config = {
        "env_prefix": "TELLO_",
        "env_file": Path(__file__).resolve().parents[2] / ".env",
        "extra": "ignore",
    }


settings = Settings()
