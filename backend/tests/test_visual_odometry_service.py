import asyncio

import numpy as np
import pytest

from app.services.optical_flow import OpticalFlowResult
from app.services.visual_odometry_service import VisualOdometryService


class FrameSource:
    is_streaming = True

    def get_frame(self):
        return np.zeros((24, 32, 3), dtype=np.uint8)


class FakeEstimator:
    def update(self, _frame):
        return OpticalFlowResult(
            tracking_valid=True,
            delta_x=0.1,
            delta_y=-0.05,
            tracked_points=12,
            quality=0.75,
        )

    def reset(self):
        pass


@pytest.mark.asyncio
async def test_visual_odometry_broadcasts_relative_position():
    service = VisualOdometryService(
        FrameSource(),
        poll_hz=30,
        estimator=FakeEstimator(),
    )
    delivered = asyncio.Event()
    messages = []

    async def receive(message):
        messages.append(message)
        delivered.set()

    service.subscribe(receive)
    await service.start()
    await asyncio.wait_for(delivered.wait(), timeout=1)
    await service.stop()

    message = messages[0]
    assert message.type == "odometry"
    assert message.data.frame_width == 32
    assert message.data.frame_height == 24
    assert message.data.position_x == pytest.approx(0.1)
    assert message.data.position_y == pytest.approx(-0.05)
    assert message.data.tracking_valid
    assert message.data.tracked_points == 12
    assert message.data.quality == pytest.approx(0.75)
