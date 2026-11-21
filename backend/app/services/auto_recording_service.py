import asyncio
import logging
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypedDict
from uuid import uuid4

from app.config import settings
from app.models.telemetry import TelemetryFrame

logger = logging.getLogger(__name__)

RecordingSender = Callable[[dict[str, Any]], Awaitable[None]]


class _RecordingAcknowledgement(TypedDict):
    ok: bool
    error: str | None


@dataclass
class _RecorderConnection:
    send: RecordingSender
    ready: bool = False


class AutoRecordingError(Exception):
    pass


class AutoRecordingService:
    REQUEST_TIMEOUT_SECONDS = 8
    TAKEOFF_ALTITUDE_GAIN_CM = 15
    LANDING_ALTITUDE_MARGIN_CM = 5

    def __init__(self) -> None:
        self._landing_speed_threshold_cm_s = (
            settings.auto_record_landing_speed_threshold_cm_s
        )
        self._landing_confirmation_samples = (
            settings.auto_record_landing_confirmation_samples
        )
        self._recorders: dict[str, _RecorderConnection] = {}
        self._pending_requests: dict[
            str, tuple[str, asyncio.Future[_RecordingAcknowledgement]]
        ] = {}
        self._request_lock = asyncio.Lock()
        self._active_recorder_id: str | None = None
        self._recording_active = False
        self._stop_pending = False
        self._monitoring_landing = False
        self._baseline_height: int | None = None
        self._airborne = False
        self._landing_samples = 0
        self._stop_task: asyncio.Task[None] | None = None

    def connect_recorder(self, send: RecordingSender) -> str:
        recorder_id = str(uuid4())
        self._recorders[recorder_id] = _RecorderConnection(send=send)
        return recorder_id

    def disconnect_recorder(self, recorder_id: str) -> None:
        self._recorders.pop(recorder_id, None)
        for pending_recorder_id, future in list(self._pending_requests.values()):
            if pending_recorder_id == recorder_id and not future.done():
                future.set_result({"ok": False, "error": "Recorder disconnected"})
        if self._active_recorder_id == recorder_id:
            self._active_recorder_id = None

    def handle_client_message(
        self, recorder_id: str, message: dict[str, Any]
    ) -> None:
        recorder = self._recorders.get(recorder_id)
        if recorder is None:
            return

        message_type = message.get("type")
        data = message.get("data")
        if not isinstance(data, dict):
            return

        if message_type == "recorder_status":
            ready = data.get("ready")
            if isinstance(ready, bool):
                recorder.ready = ready
                if ready and self._recording_active:
                    if self._active_recorder_id is None:
                        self._active_recorder_id = recorder_id
                    if (
                        self._active_recorder_id == recorder_id
                        and self._stop_pending
                        and (self._stop_task is None or self._stop_task.done())
                    ):
                        self._stop_task = asyncio.create_task(
                            self._stop_pending_recording()
                        )
        elif message_type == "recording_ack":
            request_id = data.get("request_id")
            if not isinstance(request_id, str):
                return
            pending = self._pending_requests.get(request_id)
            if pending is None or pending[0] != recorder_id or pending[1].done():
                return
            error = data.get("error")
            pending[1].set_result(
                {
                    "ok": data.get("ok") is True,
                    "error": error if isinstance(error, str) else None,
                }
            )

    async def start_recording_for_takeoff(self) -> None:
        if self._stop_task is not None and not self._stop_task.done():
            await self._stop_task
        async with self._request_lock:
            if self._recording_active:
                raise AutoRecordingError(
                    "The previous automatic recording has not stopped"
                )
            recorder_id = self._get_ready_recorder()
            if recorder_id is None:
                raise AutoRecordingError(
                    "Automatic recording requires a connected, ready browser recorder"
                )
            await self._request_recording_action(recorder_id, "start")
            self._active_recorder_id = recorder_id
            self._recording_active = True

    def monitor_landing_from_height(self, baseline_height: int) -> None:
        self._baseline_height = baseline_height
        self._airborne = False
        self._landing_samples = 0
        self._monitoring_landing = True

    def stop_recording_after_successful_land(self) -> None:
        if not self._recording_active:
            return
        if self._stop_task is not None and not self._stop_task.done():
            return
        self._monitoring_landing = False
        self._stop_task = asyncio.create_task(self._stop_after_landing())

    async def stop_recording_after_failed_takeoff(self) -> None:
        recorder_id = self._active_recorder_id
        self._monitoring_landing = False
        if not self._recording_active:
            return
        if recorder_id is None:
            self._stop_pending = True
            return

        try:
            async with self._request_lock:
                await self._request_recording_action(recorder_id, "stop")
        except AutoRecordingError:
            self._stop_pending = True
            logger.exception("Could not stop recording after takeoff failed")
        else:
            self._clear_recording_state()

    async def handle_telemetry(self, frame: TelemetryFrame) -> None:
        if not self._monitoring_landing or self._baseline_height is None:
            return

        telemetry = frame.data
        if not self._airborne:
            if telemetry.height >= (
                self._baseline_height + self.TAKEOFF_ALTITUDE_GAIN_CM
            ):
                self._airborne = True
            return

        speed = telemetry.speed
        speed_magnitude = math.sqrt(
            speed.x**2 + speed.y**2 + speed.z**2
        )
        if (
            telemetry.height
            <= self._baseline_height + self.LANDING_ALTITUDE_MARGIN_CM
            and speed_magnitude <= self._landing_speed_threshold_cm_s
        ):
            self._landing_samples += 1
        else:
            self._landing_samples = 0

        if (
            self._landing_samples >= self._landing_confirmation_samples
            and (self._stop_task is None or self._stop_task.done())
        ):
            self._monitoring_landing = False
            self._stop_task = asyncio.create_task(self._stop_after_landing())

    def _get_ready_recorder(self) -> str | None:
        if (
            self._active_recorder_id is not None
            and self._active_recorder_id in self._recorders
            and self._recorders[self._active_recorder_id].ready
        ):
            return self._active_recorder_id
        return next(
            (
                recorder_id
                for recorder_id, recorder in self._recorders.items()
                if recorder.ready
            ),
            None,
        )

    async def _request_recording_action(
        self, recorder_id: str, action: str
    ) -> None:
        recorder = self._recorders.get(recorder_id)
        if recorder is None:
            raise AutoRecordingError("The browser recorder disconnected")

        request_id = str(uuid4())
        future: asyncio.Future[_RecordingAcknowledgement] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending_requests[request_id] = (recorder_id, future)
        try:
            await recorder.send(
                {
                    "type": "recording_request",
                    "data": {"request_id": request_id, "action": action},
                }
            )
            try:
                result = await asyncio.wait_for(
                    future, timeout=self.REQUEST_TIMEOUT_SECONDS
                )
            except TimeoutError as error:
                raise AutoRecordingError(
                    f"Browser recorder did not acknowledge {action} in time"
                ) from error
        except AutoRecordingError:
            raise
        except Exception as error:
            raise AutoRecordingError(
                f"Could not request recording {action}: {error}"
            ) from error
        finally:
            self._pending_requests.pop(request_id, None)

        if not result["ok"]:
            raise AutoRecordingError(
                result.get("error") or f"Browser recorder could not {action}"
            )

    async def _stop_after_landing(self) -> None:
        recorder_id = self._active_recorder_id
        if recorder_id is None:
            self._stop_pending = True
            return

        try:
            async with self._request_lock:
                await self._request_recording_action(recorder_id, "stop")
        except AutoRecordingError:
            logger.exception("Could not stop recording after landing")
            if self._active_recorder_id is not None:
                self._monitoring_landing = True
                self._landing_samples = self._landing_confirmation_samples - 1
            self._stop_pending = True
        else:
            self._clear_recording_state()

    async def _stop_pending_recording(self) -> None:
        recorder_id = self._active_recorder_id
        if recorder_id is None:
            return
        try:
            async with self._request_lock:
                await self._request_recording_action(recorder_id, "stop")
        except AutoRecordingError:
            logger.exception("Could not complete a pending recording stop")
        else:
            self._clear_recording_state()

    def _clear_recording_state(self) -> None:
        self._active_recorder_id = None
        self._recording_active = False
        self._stop_pending = False
        self._monitoring_landing = False
        self._baseline_height = None
        self._airborne = False
        self._landing_samples = 0
