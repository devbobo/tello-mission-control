from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class VisionDetection(BaseModel):
    label: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    x_min: float = Field(ge=0, le=1)
    y_min: float = Field(ge=0, le=1)
    x_max: float = Field(ge=0, le=1)
    y_max: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> "VisionDetection":
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise ValueError("Detection bounds must have positive width and height")
        return self


class VisionFrameData(BaseModel):
    frame_id: int = Field(ge=1)
    frame_width: int = Field(gt=0)
    frame_height: int = Field(gt=0)
    model: str
    device: str
    inference_ms: float = Field(ge=0)
    detections: list[VisionDetection]


class VisionMessage(BaseModel):
    type: Literal["vision"] = "vision"
    data: VisionFrameData
    timestamp: datetime
