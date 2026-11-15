import asyncio
import threading
import time

import numpy as np
import pytest

from app.models.markers import MarkerDetection
from app.services.marker_service import MarkerDetectionService


class FrameSource:
    is_streaming = True

    def __init__(self):
        self.frame = np.zeros((4, 6, 3), dtype=np.uint8)

    def get_frame(self):
        return self.frame


class FakeMarkerDetector:
    aruco_dictionary = "DICT_4X4_50"

    def __init__(self, source):
        self.source = source
        self.started = threading.Event()

    def detect(self, frame):
        assert frame is not self.source.frame
        self.started.set()
        time.sleep(0.06)
        return [
            MarkerDetection(
                marker_type="aruco",
                marker_id="7",
                x_min=0.25,
                y_min=0.1,
                x_max=0.75,
                y_max=0.9,
            )
        ]


@pytest.mark.asyncio
async def test_marker_service_publishes_off_loop_detections():
    source = FrameSource()
    detector = FakeMarkerDetector(source)
    service = MarkerDetectionService(source, poll_hz=30, detector=detector)
    delivered = asyncio.Event()
    messages = []

    async def receive(message):
        messages.append(message)
        delivered.set()

    service.subscribe(receive)
    await service.start()
    assert await asyncio.to_thread(detector.started.wait, 1)

    ticks = 0

    async def keep_loop_responsive():
        nonlocal ticks
        while not delivered.is_set():
            ticks += 1
            await asyncio.sleep(0.005)

    ticker = asyncio.create_task(keep_loop_responsive())
    await asyncio.wait_for(delivered.wait(), timeout=2)
    await ticker
    await service.stop()

    message = messages[0]
    assert message.type == "markers"
    assert message.data.frame_width == 6
    assert message.data.frame_height == 4
    assert message.data.aruco_dictionary == "DICT_4X4_50"
    assert message.data.markers[0].marker_id == "7"
    assert message.timestamp.tzinfo is not None
    assert ticks > 0


@pytest.mark.asyncio
async def test_marker_service_stays_idle_without_subscribers():
    source = FrameSource()
    detector = FakeMarkerDetector(source)
    service = MarkerDetectionService(source, poll_hz=30, detector=detector)

    await service.start()
    await asyncio.sleep(0.05)
    await service.stop()

    assert not detector.started.is_set()


def test_marker_service_rejects_non_positive_poll_frequency():
    with pytest.raises(ValueError, match="greater than zero"):
        MarkerDetectionService(FrameSource(), poll_hz=0)
