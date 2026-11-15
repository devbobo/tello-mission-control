from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Protocol, Sequence

import numpy as np
from numpy.typing import NDArray

from app.models.vision import VisionDetection, VisionMessage
from app.services.drone_manager import DroneManager

logger = logging.getLogger(__name__)

VisionSubscriber = Callable[[VisionMessage], Awaitable[None]]


class VisionDetector(Protocol):
    @property
    def model_name(self) -> str: ...

    def detect(self, frame: NDArray[np.uint8]) -> Sequence[VisionDetection]: ...


class VisionService:
    """Runs one detector at a time against fresh snapshots of the latest video frame."""

    def __init__(
        self,
        drone_manager: DroneManager,
        detector: VisionDetector | None,
        inference_hz: float,
        model_path: Path | None = None,
        device: str = "auto",
    ) -> None:
        if inference_hz <= 0:
            raise ValueError("Vision inference frequency must be greater than zero")
        self._drone_manager = drone_manager
        self._detector = detector
        self._inference_hz = inference_hz
        self._model_path = model_path
        self._device = device
        self._subscribers: set[VisionSubscriber] = set()
        self._task: asyncio.Task | None = None
        self._running = False
        self._frame_id = 0

    @property
    def model_path(self) -> Path | None:
        return self._model_path

    def subscribe(self, callback: VisionSubscriber) -> None:
        self._subscribers.add(callback)

    def unsubscribe(self, callback: VisionSubscriber) -> None:
        self._subscribers.discard(callback)

    async def start(self) -> None:
        if self._task is not None:
            return
        if self._detector is None:
            logger.info("Vision inference idle: no detector is configured")
            return
        self._running = True
        self._task = asyncio.create_task(self._inference_loop())
        logger.info("VisionService started at %.1f Hz on %s", self._inference_hz, self._device)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("VisionService stopped")

    async def _inference_loop(self) -> None:
        detector = self._detector
        if detector is None:
            return

        loop = asyncio.get_running_loop()
        interval = 1.0 / self._inference_hz
        next_run = loop.time()

        while self._running:
            if self._drone_manager.is_streaming and self._subscribers:
                try:
                    frame = await asyncio.to_thread(self._copy_latest_frame)
                    if frame is not None:
                        captured_at = datetime.now(timezone.utc)
                        started_at = time.perf_counter()
                        raw_detections = await self._run_detector(
                            detector, frame
                        )
                        detections = [
                            VisionDetection.model_validate(detection)
                            for detection in raw_detections
                        ]
                        self._frame_id += 1
                        message = VisionMessage(
                            data={
                                "frame_id": self._frame_id,
                                "frame_width": int(frame.shape[1]),
                                "frame_height": int(frame.shape[0]),
                                "model": detector.model_name,
                                "device": self._device,
                                "inference_ms": (
                                    time.perf_counter() - started_at
                                )
                                * 1000,
                                "detections": detections,
                            },
                            timestamp=captured_at,
                        )
                        await self._broadcast(message)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Vision inference failed")

            next_run += interval
            await asyncio.sleep(max(0, next_run - loop.time()))
            if next_run < loop.time():
                next_run = loop.time()

    def _copy_latest_frame(self) -> NDArray[np.uint8] | None:
        frame = self._drone_manager.get_frame()
        return frame.copy() if frame is not None else None

    async def _run_detector(
        self, detector: VisionDetector, frame: NDArray[np.uint8]
    ) -> Sequence[VisionDetection]:
        inference = asyncio.create_task(asyncio.to_thread(detector.detect, frame))
        try:
            return await asyncio.shield(inference)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(inference)
            except Exception:
                logger.exception("Vision detector failed while stopping")
            raise

    async def _broadcast(self, message: VisionMessage) -> None:
        dead: list[VisionSubscriber] = []
        for callback in tuple(self._subscribers):
            try:
                await callback(message)
            except Exception:
                logger.exception("Vision subscriber failed; removing it")
                dead.append(callback)
        for callback in dead:
            self._subscribers.discard(callback)
