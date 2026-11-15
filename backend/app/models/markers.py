from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class MarkerDetection(BaseModel):
    marker_type: Literal["qr", "aruco"]
    marker_id: str = Field(min_length=1, max_length=64)
    payload: str | None = Field(default=None, max_length=256)
    payload_truncated: bool = False
    x_min: float = Field(ge=0, le=1)
    y_min: float = Field(ge=0, le=1)
    x_max: float = Field(ge=0, le=1)
    y_max: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> "MarkerDetection":
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError("Marker bounds must have positive width and height")
        return self


class MarkerFrameData(BaseModel):
    frame_id: int = Field(ge=1)
    frame_width: int = Field(gt=0)
    frame_height: int = Field(gt=0)
    inference_ms: float = Field(ge=0)
    aruco_dictionary: str
    markers: list[MarkerDetection]


class MarkerMessage(BaseModel):
    type: Literal["markers"] = "markers"
    data: MarkerFrameData
    timestamp: datetime
