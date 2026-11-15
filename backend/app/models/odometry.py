from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OdometryData(BaseModel):
    frame_id: int = Field(ge=1)
    frame_width: int = Field(gt=0)
    frame_height: int = Field(gt=0)
    position_x: float
    position_y: float
    delta_x: float
    delta_y: float
    tracking_valid: bool
    tracked_points: int = Field(ge=0)
    quality: float = Field(ge=0, le=1)


class OdometryMessage(BaseModel):
    type: Literal["odometry"] = "odometry"
    data: OdometryData
    timestamp: datetime
