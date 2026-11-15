from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Awaitable, Callable

import numpy as np
from numpy.typing import NDArray

from app.models.odometry import OdometryMessage
from app.services.drone_manager import DroneManager
from app.services.optical_flow import OpticalFlowEstimator, OpticalFlowResult

logger = logging.getLogger(__name__)

OdometrySubscriber = Callable[[OdometryMessage], Awaitable[None]]


class VisualOdometryService:
    """Publishes relative image-space motion estimates from fresh video frames."""

    def __init__(
        self,
        drone_manager: DroneManager,
        poll_hz: float = 5.0,
        estimator: OpticalFlowEstimator | None = None,
    ) -> None:
        if poll_hz <= 0:
            raise ValueError("Odometry poll frequency must be greater than zero")
        self._drone_manager = drone_manager
        self._poll_hz = poll_hz
        self._estimator = estimator or OpticalFlowEstimator()
        self._subscribers: set[OdometrySubscriber] = set()
        self._task: asyncio.Task | None = None
        self._running = False
        self._active = False
        self._frame_id = 0
        self._position_x = 0.0
        self._position_y = 0.0

    def subscribe(self, callback: OdometrySubscriber) -> None:
        self._subscribers.add(callback)

    def unsubscribe(self, callback: OdometrySubscriber) -> None:
        self._subscribers.discard(callback)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("VisualOdometryService started at %.1f Hz", self._poll_hz)

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("VisualOdometryService stopped")

    async def _poll_loop(self) -> None:
        loop = asyncio.get_running_loop()
        interval = 1.0 / self._poll_hz
        next_run = loop.time()

        while self._running:
            if self._drone_manager.is_streaming and self._subscribers:
                try:
                    frame = await asyncio.to_thread(self._copy_latest_frame)
                    if frame is None:
                        await self._reset_tracking()
                    else:
                        self._active = True
                        started_at = time.perf_counter()
                        result = await self._estimate(frame)
                        self._frame_id += 1
                        if result.tracking_valid:
                            self._position_x += result.delta_x
                            self._position_y += result.delta_y
                        message = OdometryMessage(
                            data={
                                "frame_id": self._frame_id,
                                "frame_width": int(frame.shape[1]),
                                "frame_height": int(frame.shape[0]),
                                "position_x": self._position_x,
                                "position_y": self._position_y,
                                "delta_x": (
                                    result.delta_x if result.tracking_valid else 0
                                ),
                                "delta_y": (
                                    result.delta_y if result.tracking_valid else 0
                                ),
                                "tracking_valid": result.tracking_valid,
                                "tracked_points": result.tracked_points,
                                "quality": result.quality,
                            },
                            timestamp=datetime.now(timezone.utc),
                        )
                        logger.debug(
                            "Visual odometry processed frame in %.1f ms",
                            (time.perf_counter() - started_at) * 1000,
                        )
                        await self._broadcast(message)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Visual odometry update failed")
            elif self._active:
                await self._reset_tracking()

            next_run += interval
            await asyncio.sleep(max(0, next_run - loop.time()))
            if next_run < loop.time():
                next_run = loop.time()

    def _copy_latest_frame(self) -> NDArray[np.uint8] | None:
        frame = self._drone_manager.get_frame()
        return frame.copy() if frame is not None else None

    async def _estimate(self, frame: NDArray[np.uint8]) -> OpticalFlowResult:
        inference = asyncio.create_task(asyncio.to_thread(self._estimator.update, frame))
        try:
            return await asyncio.shield(inference)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(inference)
            except Exception:
                logger.exception("Optical flow failed while stopping")
            raise

    async def _reset_tracking(self) -> None:
        if self._active:
            await asyncio.to_thread(self._estimator.reset)
            self._active = False

    async def _broadcast(self, message: OdometryMessage) -> None:
        dead: list[OdometrySubscriber] = []
        for callback in tuple(self._subscribers):
            try:
                await callback(message)
            except Exception:
                logger.exception("Odometry subscriber failed; removing it")
                dead.append(callback)
        for callback in dead:
            self._subscribers.discard(callback)
