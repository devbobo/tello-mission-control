from typing import Literal

from pydantic import BaseModel, Field


class WebRTCOffer(BaseModel):
    sdp: str = Field(min_length=1, max_length=1_000_000)
    type: Literal["offer"]


class WebRTCAnswer(BaseModel):
    sdp: str
    type: Literal["answer"]
    peer_id: str


class WebRTCIceServer(BaseModel):
    urls: str | list[str]
    username: str | None = None
    credential: str | None = None
