from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Callable

import cv2

from app.config import settings
from app.models.commands import MoveDirection, RotateDirection

logger = logging.getLogger(__name__)


class DroneNotConnectedError(Exception):
    pass


class DroneNotFlyingError(Exception):
    pass


class DroneCommandBusyError(Exception):
    pass


class MockTello:
    """Fake Tello for development without a physical drone."""

    def __init__(self) -> None:
        self._connected = False
        self._flying = False
        self._battery = 85
        self._height = 0
        self._flight_time = 0
        self._yaw = 0
        self._pitch = 0
        self._roll = 0
        self._speed_x = 0
        self._speed_y = 0
        self._speed_z = 0
        self._barometer = 0.0
        self._temp_high = 65.0
        self._temp_low = 60.0
        self.last_rc_control = (0, 0, 0, 0)

    def _reset_flight_state(self) -> None:
        self._flying = False
        self._height = 0
        self._barometer = 0.0
        self._speed_x = 0
        self._speed_y = 0
        self._speed_z = 0

    def connect(self) -> None:
        self._connected = True
        logger.info("MockTello: connected")

    def end(self) -> None:
        self._connected = False
        self._flying = False
        self._height = 0
        self._barometer = 0.0
        logger.info("MockTello: disconnected")

    def takeoff(self) -> None:
        self._flying = True
        self._height = 50
        self._barometer = 50.0
        logger.info("MockTello: takeoff")

    def land(self) -> None:
        self._reset_flight_state()
        logger.info("MockTello: land")

    def emergency(self) -> None:
        self._reset_flight_state()
        logger.info("MockTello: emergency stop")

    def move_forward(self, x: int) -> None:
        self._speed_y = x
        logger.info("MockTello: move_forward %dcm", x)

    def move_back(self, x: int) -> None:
        self._speed_y = -x
        logger.info("MockTello: move_back %dcm", x)

    def move_left(self, x: int) -> None:
        self._speed_x = -x
        logger.info("MockTello: move_left %dcm", x)

    def move_right(self, x: int) -> None:
        self._speed_x = x
        logger.info("MockTello: move_right %dcm", x)

    def move_up(self, x: int) -> None:
        self._height += x
        self._barometer = float(self._height)
        self._speed_z = x
        logger.info("MockTello: move_up %dcm", x)

    def move_down(self, x: int) -> None:
        self._height = max(0, self._height - x)
        self._barometer = float(self._height)
        self._speed_z = -x
        logger.info("MockTello: move_down %dcm", x)

    def rotate_clockwise(self, x: int) -> None:
        self._yaw = (self._yaw + x) % 360
        logger.info("MockTello: rotate_cw %ddeg", x)

    def rotate_counter_clockwise(self, x: int) -> None:
        self._yaw = (self._yaw - x) % 360
        logger.info("MockTello: rotate_ccw %ddeg", x)

    def send_rc_control(self, lr: int, fb: int, ud: int, yaw: int) -> None:
        self.last_rc_control = (lr, fb, ud, yaw)
        self._speed_x = lr
        self._speed_y = fb
        self._speed_z = ud
        logger.info("MockTello: rc_control %s", self.last_rc_control)

    # -- Telemetry getters (matching djitellopy.Tello API) --

    def get_battery(self) -> int:
        return self._battery

    def get_height(self) -> int:
        return self._height

    def get_flight_time(self) -> int:
        return self._flight_time

    def get_highest_temperature(self) -> float:
        return self._temp_high

    def get_lowest_temperature(self) -> float:
        return self._temp_low

    def get_pitch(self) -> int:
        return self._pitch

    def get_roll(self) -> int:
        return self._roll

    def get_yaw(self) -> int:
        return self._yaw

    def get_speed_x(self) -> int:
        return self._speed_x

    def get_speed_y(self) -> int:
        return self._speed_y

    def get_speed_z(self) -> int:
        return self._speed_z

    def get_barometer(self) -> float:
        return self._barometer

    def get_distance_tof(self) -> int:
        return self._height

    # -- Video --

    def streamon(self) -> None:
        logger.info("MockTello: stream on")

    def streamoff(self) -> None:
        logger.info("MockTello: stream off")

    def get_frame_read(self) -> "MockFrameRead":
        return MockFrameRead()


class MockFrameRead:
    """Fake frame reader that generates a placeholder test pattern."""

    @property
    def frame(self):
        import numpy as np

        # 960x720 dark frame with text overlay
        img = np.zeros((720, 960, 3), dtype=np.uint8)
        img[:] = (40, 40, 40)  # dark gray background

        try:
            import cv2

            cv2.putText(
                img, "MOCK DRONE", (280, 340),
                cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3,
            )
            cv2.putText(
                img, "No drone connected", (310, 400),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (180, 180, 180), 1,
            )
        except ImportError:
            pass

        return img


class DroneManager:
    """Singleton service owning the Tello connection.

    All commands are serialized through an asyncio.Lock.
    Blocking djitellopy calls are offloaded via asyncio.to_thread().
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._tello: Any | None = None
        self._connected: bool = False
        self._flying: bool = False
        self._streaming: bool = False
        self._frame_read: Any | None = None
        self._command_log_callbacks: list[Callable] = []
        self._last_rc_control = (0, 0, 0, 0)
        self._last_rc_control_at = 0.0

    # -- Properties --

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_flying(self) -> bool:
        return self._flying

    @property
    def is_streaming(self) -> bool:
        return self._streaming

    @property
    def tello(self) -> Any | None:
        return self._tello

    # -- Command log broadcasting --

    def add_command_log_callback(self, callback: Callable) -> None:
        self._command_log_callbacks.append(callback)

    def remove_command_log_callback(self, callback: Callable) -> None:
        try:
            self._command_log_callbacks.remove(callback)
        except ValueError:
            pass

    async def _broadcast_command_log(
        self,
        command: str,
        params: dict,
        result: str,
        error: str | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        entry = {
            "type": "command_log",
            "data": {
                "command": command,
                "params": params,
                "result": result,
                "error": error,
                "timestamp": (occurred_at or datetime.now(timezone.utc)).isoformat(),
            },
        }
        dead: list[Callable] = []
        for cb in self._command_log_callbacks:
            try:
                await cb(entry)
            except Exception:
                logger.exception("Command log subscriber failed; removing it")
                dead.append(cb)
        for cb in dead:
            try:
                self._command_log_callbacks.remove(cb)
            except ValueError:
                pass

    async def log_command_failure(
        self,
        command: str,
        params: dict,
        error: str,
        occurred_at: datetime | None = None,
    ) -> None:
        await self._broadcast_command_log(
            command, params, "error", error, occurred_at
        )

    # -- Core execute method --

    async def execute(
        self, fn: Callable, *args: Any, reset_rc: bool = False
    ) -> tuple[Any, datetime]:
        """Execute a blocking djitellopy method with lock serialization."""
        async with self._lock:
            if reset_rc and self._last_rc_control != (0, 0, 0, 0):
                rc_timestamp = await self._send_rc_control_locked((0, 0, 0, 0))
                self._last_rc_control = (0, 0, 0, 0)
                await self._broadcast_command_log(
                    "rc_control",
                    {"lr": 0, "fb": 0, "ud": 0, "yaw": 0},
                    "ok",
                    occurred_at=rc_timestamp,
                )
            command_timestamp = datetime.now(timezone.utc)
            result = await asyncio.to_thread(fn, *args)
            return result, command_timestamp

    async def _send_rc_control_locked(
        self, values: tuple[int, int, int, int]
    ) -> datetime:
        interval = float(
            getattr(self._tello, "TIME_BTW_RC_CONTROL_COMMANDS", 0.1)
        )
        delay = interval - (monotonic() - self._last_rc_control_at)
        if delay > 0:
            await asyncio.sleep(delay)
        command_timestamp = datetime.now(timezone.utc)
        await asyncio.to_thread(self._tello.send_rc_control, *values)
        self._last_rc_control_at = monotonic()
        return command_timestamp

    # -- Connection --

    async def connect(self) -> dict:
        if self._connected:
            battery = await self.get_battery()
            return {"ok": True, "status": "already_connected", "battery": battery}

        if settings.use_mock_drone:
            self._tello = MockTello()
        else:
            from djitellopy import Tello

            self._tello = Tello(host=settings.tello_host)
            self._tello.RETRY_COUNT = settings.tello_retry_count

        _, command_timestamp = await self.execute(self._tello.connect)
        self._connected = True
        battery = await self.get_battery()
        await self._broadcast_command_log(
            "connect", {}, "ok", occurred_at=command_timestamp
        )
        return {"ok": True, "status": "connected", "battery": battery}

    async def disconnect(self) -> dict:
        if not self._connected:
            return {"ok": True, "status": "already_disconnected"}

        await self._reset_rc_control()

        if self._streaming:
            command_timestamp = datetime.now(timezone.utc)
            try:
                _, command_timestamp = await self.execute(self._tello.streamoff)
                await self._broadcast_command_log(
                    "stream_off", {}, "ok", occurred_at=command_timestamp
                )
            except Exception as e:
                logger.warning("Failed to stop stream during disconnect: %s", e)
                await self._broadcast_command_log(
                    "stream_off", {}, "error", str(e), command_timestamp
                )
            self._streaming = False
            self._frame_read = None

        if self._flying:
            command_timestamp = datetime.now(timezone.utc)
            try:
                _, command_timestamp = await self.execute(self._tello.land)
                await self._broadcast_command_log(
                    "land", {}, "ok", occurred_at=command_timestamp
                )
            except Exception as e:
                logger.warning("Failed to land during disconnect: %s", e)
                await self._broadcast_command_log(
                    "land", {}, "error", str(e), command_timestamp
                )
            self._flying = False

        _, command_timestamp = await self.execute(self._tello.end)
        self._connected = False
        self._tello = None
        self._last_rc_control = (0, 0, 0, 0)
        await self._broadcast_command_log(
            "disconnect", {}, "ok", occurred_at=command_timestamp
        )
        return {"ok": True, "status": "disconnected"}

    # -- Flight commands --

    async def takeoff(self) -> dict:
        self._require_connected()
        _, command_timestamp = await self.execute(self._tello.takeoff)
        self._flying = True
        await self._broadcast_command_log(
            "takeoff", {}, "ok", occurred_at=command_timestamp
        )
        return {"ok": True, "message": "Takeoff successful"}

    async def land(self) -> dict:
        self._require_connected()
        _, command_timestamp = await self.execute(self._tello.land, reset_rc=True)
        self._flying = False
        self._last_rc_control = (0, 0, 0, 0)
        await self._broadcast_command_log(
            "land", {}, "ok", occurred_at=command_timestamp
        )
        return {"ok": True, "message": "Landing successful"}

    async def send_rc_control(self, lr: int, fb: int, ud: int, yaw: int) -> dict:
        self._require_connected()
        values = (lr, fb, ud, yaw)
        if any(value < -100 or value > 100 for value in values):
            raise ValueError("RC control values must be between -100 and 100")
        if values != (0, 0, 0, 0):
            self._require_flying()
        if self._lock.locked():
            raise DroneCommandBusyError("Another drone command is in progress")

        async with self._lock:
            command_timestamp = await self._send_rc_control_locked(values)
        if values != self._last_rc_control:
            self._last_rc_control = values
            await self._broadcast_command_log(
                "rc_control",
                {"lr": lr, "fb": fb, "ud": ud, "yaw": yaw},
                "ok",
                occurred_at=command_timestamp,
            )
        return {"ok": True, "message": "RC control sent"}

    async def _reset_rc_control(self) -> None:
        if self._last_rc_control == (0, 0, 0, 0) or not self._tello:
            return
        values = (0, 0, 0, 0)
        try:
            async with self._lock:
                command_timestamp = await self._send_rc_control_locked(values)
        except Exception as e:
            logger.warning("Failed to reset RC control: %s", e)
            await self._broadcast_command_log(
                "rc_control",
                {"lr": 0, "fb": 0, "ud": 0, "yaw": 0},
                "error",
                str(e),
            )
        else:
            self._last_rc_control = values
            await self._broadcast_command_log(
                "rc_control",
                {"lr": 0, "fb": 0, "ud": 0, "yaw": 0},
                "ok",
                occurred_at=command_timestamp,
            )

    async def emergency(self) -> dict:
        """Emergency stop — bypasses the lock for instant response."""
        command_timestamp = datetime.now(timezone.utc)
        if self._tello:
            await asyncio.to_thread(self._tello.emergency)
            self._flying = False
            self._last_rc_control = (0, 0, 0, 0)
        await self._broadcast_command_log(
            "emergency", {}, "ok", occurred_at=command_timestamp
        )
        return {"ok": True, "message": "Emergency stop executed"}

    # -- Movement --

    async def move(self, direction: MoveDirection, distance_cm: int) -> dict:
        self._require_connected()
        self._require_flying()
        method_map = {
            MoveDirection.forward: self._tello.move_forward,
            MoveDirection.back: self._tello.move_back,
            MoveDirection.left: self._tello.move_left,
            MoveDirection.right: self._tello.move_right,
            MoveDirection.up: self._tello.move_up,
            MoveDirection.down: self._tello.move_down,
        }
        fn = method_map[direction]
        _, command_timestamp = await self.execute(fn, distance_cm, reset_rc=True)
        await self._broadcast_command_log(
            "move",
            {"direction": direction.value, "distance_cm": distance_cm},
            "ok",
            occurred_at=command_timestamp,
        )
        return {"ok": True, "message": f"Moved {direction.value} {distance_cm}cm"}

    # -- Rotation --

    async def rotate(self, direction: RotateDirection, angle_deg: int) -> dict:
        self._require_connected()
        self._require_flying()
        if direction == RotateDirection.cw:
            _, command_timestamp = await self.execute(
                self._tello.rotate_clockwise, angle_deg, reset_rc=True
            )
        else:
            _, command_timestamp = await self.execute(
                self._tello.rotate_counter_clockwise, angle_deg, reset_rc=True
            )
        await self._broadcast_command_log(
            "rotate",
            {"direction": direction.value, "angle_deg": angle_deg},
            "ok",
            occurred_at=command_timestamp,
        )
        return {"ok": True, "message": f"Rotated {direction.value} {angle_deg}°"}

    # -- Video streaming --

    async def stream_on(self) -> dict:
        self._require_connected()
        if self._streaming:
            return {"ok": True, "message": "Stream already active"}
        _, command_timestamp = await self.execute(self._tello.streamon)
        self._frame_read = await asyncio.to_thread(self._tello.get_frame_read)
        self._streaming = True
        await self._broadcast_command_log(
            "stream_on", {}, "ok", occurred_at=command_timestamp
        )
        return {"ok": True, "message": "Video stream started"}

    async def stream_off(self) -> dict:
        self._require_connected()
        if not self._streaming:
            return {"ok": True, "message": "Stream already stopped"}
        _, command_timestamp = await self.execute(self._tello.streamoff)
        self._frame_read = None
        self._streaming = False
        await self._broadcast_command_log(
            "stream_off", {}, "ok", occurred_at=command_timestamp
        )
        return {"ok": True, "message": "Video stream stopped"}

    def get_frame(self):
        """Get the current frame as an OpenCV-compatible BGR array."""
        if not self._frame_read:
            return None
        return cv2.cvtColor(self._frame_read.frame, cv2.COLOR_RGB2BGR)

    # -- Telemetry (no lock needed — reads cached state) --

    async def get_battery(self) -> int:
        if not self._tello:
            return 0
        return await asyncio.to_thread(self._tello.get_battery)

    async def get_telemetry(self) -> dict:
        if not self._tello:
            return {
                "battery": 0, "height": 0, "flight_time": 0,
                "temperature": {"high": 0.0, "low": 0.0},
                "attitude": {"pitch": 0, "roll": 0, "yaw": 0},
                "speed": {"x": 0, "y": 0, "z": 0},
                "barometer": 0.0, "tof_distance": 0,
            }
        t = self._tello

        def _read_all() -> dict:
            return {
                "battery": t.get_battery(),
                "height": t.get_height(),
                "flight_time": t.get_flight_time(),
                "temperature": {
                    "high": t.get_highest_temperature(),
                    "low": t.get_lowest_temperature(),
                },
                "attitude": {
                    "pitch": t.get_pitch(),
                    "roll": t.get_roll(),
                    "yaw": t.get_yaw(),
                },
                "speed": {
                    "x": t.get_speed_x(),
                    "y": t.get_speed_y(),
                    "z": t.get_speed_z(),
                },
                "barometer": t.get_barometer(),
                "tof_distance": t.get_distance_tof(),
            }

        return await asyncio.to_thread(_read_all)

    # -- Guards --

    def _require_connected(self) -> None:
        if not self._connected:
            raise DroneNotConnectedError("Drone is not connected")

    def _require_flying(self) -> None:
        if not self._flying:
            raise DroneNotFlyingError("Drone is not flying (call takeoff first)")

    # -- Cleanup --

    async def shutdown(self) -> None:
        if self._connected:
            try:
                await self.disconnect()
            except Exception as e:
                logger.error("Error during shutdown disconnect: %s", e)
