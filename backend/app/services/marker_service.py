from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable, Protocol, Sequence

import numpy as np
from numpy.typing import NDArray

from app.models.markers import MarkerDetection, MarkerMessage
from app.services.drone_manager import DroneManager
from app.services.marker_detector import OpenCVMarkerDetector

logger = logging.getLogger(__name__)

MarkerSubscriber = Callable[[MarkerMessage], Awaitable[None]]


class MarkerDetector(Protocol):
    aruco_dictionary: str

    def detect(self, frame: NDArray[np.uint8]) -> Sequence[MarkerDetection]: ...


class MarkerDetectionService:
    """Publishes QR and ArUco detections from fresh video snapshots."""

    def __init__(
        self,
        drone_manager: DroneManager,
        poll_hz: float = 5.0,
        aruco_dictionary: str = "DICT_4X4_50",
        detector: MarkerDetector | None = None,
    ) -> None:
        if poll_hz <= 0:
            raise ValueError("Marker detection frequency must be greater than zero")
        self._drone_manager = drone_manager
        self._poll_hz = poll_hz
        self._detector = detector or OpenCVMarkerDetector(aruco_dictionary)
        self._subscribers: set[MarkerSubscriber] = set()
        self._task: asyncio.Task | None = None
        self._running = False
        self._frame_id = 0

    def subscribe(self, callback: MarkerSubscriber) -> None:
        self._subscribers.add(callback)

    def unsubscribe(self, callback: MarkerSubscriber) -> None:
        self._subscribers.discard(callback)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("MarkerDetectionService started at %.1f Hz", self._poll_hz)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("MarkerDetectionService stopped")

    async def _poll_loop(self) -> None:
        loop = asyncio.get_running_loop()
        interval = 1.0 / self._poll_hz
        next_run = loop.time()

        while self._running:
            if self._drone_manager.is_streaming and self._subscribers:
                try:
                    frame = await asyncio.to_thread(self._copy_latest_frame)
                    if frame is not None:
                        started_at = time.perf_counter()
                        markers = await self._detect(frame)
                        self._frame_id += 1
                        message = MarkerMessage(
                            data={
                                "frame_id": self._frame_id,
                                "frame_width": int(frame.shape[1]),
                                "frame_height": int(frame.shape[0]),
                                "inference_ms": (
                                    time.perf_counter() - started_at
                                )
                                * 1000,
                                "aruco_dictionary": self._detector.aruco_dictionary,
                                "markers": markers,
                            },
                            timestamp=datetime.now(timezone.utc),
                        )
                        await self._broadcast(message)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Marker detection update failed")

            next_run += interval
            await asyncio.sleep(max(0, next_run - loop.time()))
            if next_run < loop.time():
                next_run = loop.time()

    def _copy_latest_frame(self) -> NDArray[np.uint8] | None:
        frame = self._drone_manager.get_frame()
        return frame.copy() if frame is not None else None

    async def _detect(
        self, frame: NDArray[np.uint8]
    ) -> Sequence[MarkerDetection]:
        inference = asyncio.create_task(asyncio.to_thread(self._detector.detect, frame))
        try:
            return await asyncio.shield(inference)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(inference)
            except Exception:
                logger.exception("Marker detector failed while stopping")
            raise

    async def _broadcast(self, message: MarkerMessage) -> None:
        dead: list[MarkerSubscriber] = []
        for callback in tuple(self._subscribers):
            try:
                await callback(message)
            except Exception:
                logger.exception("Marker subscriber failed; removing it")
                dead.append(callback)
        for callback in dead:
            self._subscribers.discard(callback)
