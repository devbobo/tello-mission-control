from pathlib import Path
from typing import Any

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings

from app.models.video import WebRTCIceServer


class Settings(BaseSettings):
    # Drone connection
    tello_host: str = Field(
        default="192.168.10.1",
        validation_alias=AliasChoices("TELLO_HOST", "TELLO_TELLO_HOST"),
    )
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

    # Mock mode (for development/testing without a physical drone)
    use_mock_drone: bool = False

    @model_validator(mode="before")
    @classmethod
    def prefer_explicit_drone_host(cls, values: Any) -> Any:
        if isinstance(values, dict) and "tello_host" in values:
            values["TELLO_HOST"] = values.pop("tello_host")
        return values

    model_config = {
        "env_prefix": "TELLO_",
        "env_file": Path(__file__).resolve().parents[2] / ".env",
        "extra": "ignore",
        "populate_by_name": True,
    }


settings = Settings()
