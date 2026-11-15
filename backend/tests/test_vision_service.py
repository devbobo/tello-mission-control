import asyncio
import threading
import time
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from app.models.vision import VisionDetection
from app.services.vision_service import VisionService


class FrameSource:
    is_streaming = True

    def __init__(self):
        self.frame = np.zeros((4, 6, 3), dtype=np.uint8)

    def get_frame(self):
        return self.frame


class SlowDetector:
    model_name = "fake-detector"

    def __init__(self, source):
        self.source = source
        self.started = threading.Event()
        self._active = 0
        self._max_active = 0
        self._lock = threading.Lock()

    @property
    def max_active(self):
        return self._max_active

    @property
    def active(self):
        return self._active

    def detect(self, frame):
        assert frame is not self.source.frame
        with self._lock:
            self._active += 1
            self._max_active = max(self._max_active, self._active)
        self.started.set()
        time.sleep(0.06)
        with self._lock:
            self._active -= 1
        return [
            VisionDetection(
                label="person",
                confidence=0.9,
                x_min=0.1,
                y_min=0.2,
                x_max=0.7,
                y_max=0.8,
            )
        ]


class BlockingDetector(SlowDetector):
    def __init__(self, source):
        super().__init__(source)
        self.release = threading.Event()

    def detect(self, frame):
        self.started.set()
        self.release.wait(timeout=2)
        return super().detect(frame)


@pytest.mark.asyncio
async def test_vision_service_offloads_single_latest_frame_inference():
    source = FrameSource()
    detector = SlowDetector(source)
    service = VisionService(
        source,
        detector,
        inference_hz=30,
        model_path=Path("models/detector.onnx"),
        device="cpu",
    )
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
    assert message.type == "vision"
    assert message.data.frame_width == 6
    assert message.data.frame_height == 4
    assert message.data.model == "fake-detector"
    assert message.data.device == "cpu"
    assert message.data.detections[0].x_min == 0.1
    assert message.data.detections[0].track_id == 1
    assert message.timestamp.tzinfo is not None
    assert ticks > 0
    assert detector.max_active == 1
    assert service.model_path == Path("models/detector.onnx")


@pytest.mark.asyncio
async def test_stopping_vision_waits_for_in_flight_thread():
    source = FrameSource()
    detector = BlockingDetector(source)
    service = VisionService(source, detector, inference_hz=30)

    async def receive(_message):
        pass

    service.subscribe(receive)
    await service.start()
    assert await asyncio.to_thread(detector.started.wait, 1)

    stopping = asyncio.create_task(service.stop())
    await asyncio.sleep(0.01)
    assert not stopping.done()

    detector.release.set()
    await asyncio.wait_for(stopping, timeout=2)
    assert detector.active == 0


@pytest.mark.asyncio
async def test_vision_service_stays_idle_without_detector():
    service = VisionService(FrameSource(), None, inference_hz=5)

    await service.start()

    assert service._task is None
    await service.stop()


def test_vision_detection_requires_normalized_positive_bounds():
    with pytest.raises(ValidationError):
        VisionDetection(
            label="person",
            confidence=1.1,
            x_min=0,
            y_min=0,
            x_max=1,
            y_max=1,
        )

    with pytest.raises(ValidationError):
        VisionDetection(
            label="person",
            confidence=0.9,
            x_min=0.8,
            y_min=0.2,
            x_max=0.2,
            y_max=0.8,
        )
