import json
from enum import Enum

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

from app.config import settings


class MoveDirection(str, Enum):
    forward = "forward"
    back = "back"
    left = "left"
    right = "right"
    up = "up"
    down = "down"


class RotateDirection(str, Enum):
    cw = "cw"
    ccw = "ccw"

mcp = FastMCP("Tello Web Controller")


class BackendApi:
    """HTTP client for the existing FastAPI control surface."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._transport = transport

    async def request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> str:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.request(method, path, json=payload)
        except httpx.RequestError as exc:
            raise ToolError(
                f"Could not reach the Tello backend at {self._base_url}: {exc}"
            ) from exc

        try:
            result = response.json()
        except (ValueError, UnicodeError) as exc:
            raise ToolError(
                f"The Tello backend returned a non-JSON response "
                f"(HTTP {response.status_code})"
            ) from exc

        if not response.is_success:
            detail = result.get("detail", result) if isinstance(result, dict) else result
            raise ToolError(
                f"Tello backend returned HTTP {response.status_code}: "
                f"{json.dumps(detail, ensure_ascii=False)}"
            )

        return json.dumps(result, ensure_ascii=False)


backend_api = BackendApi(
    settings.mcp_api_url,
    timeout=settings.mcp_request_timeout,
)


@mcp.tool()
async def get_drone_status() -> str:
    """Read whether the drone is connected, flying, or streaming, and its battery."""
    return await backend_api.request("GET", "/api/status")


@mcp.tool()
async def connect_drone() -> str:
    """Connect to the Tello. Only do this when the user explicitly requests it."""
    return await backend_api.request("POST", "/api/control/connect")


@mcp.tool()
async def disconnect_drone() -> str:
    """Disconnect from the Tello; the backend lands first if it is airborne."""
    return await backend_api.request("POST", "/api/control/disconnect")


@mcp.tool()
async def takeoff() -> str:
    """Take off. This physically flies the drone; require an explicit user request."""
    return await backend_api.request("POST", "/api/control/takeoff")


@mcp.tool()
async def land() -> str:
    """Land the drone."""
    return await backend_api.request("POST", "/api/control/land")


@mcp.tool()
async def emergency_stop() -> str:
    """Immediately stop the drone motors. Use only for an emergency."""
    return await backend_api.request("POST", "/api/control/emergency")


@mcp.tool()
async def move(
    direction: MoveDirection,
    distance_cm: int,
) -> str:
    """Move while airborne, between 20 and 500 cm in one allowed direction."""
    if not 20 <= distance_cm <= 500:
        raise ToolError("distance_cm must be between 20 and 500")
    return await backend_api.request(
        "POST",
        "/api/control/move",
        {"direction": direction.value, "distance_cm": distance_cm},
    )


@mcp.tool()
async def rotate(
    direction: RotateDirection,
    angle_deg: int,
) -> str:
    """Rotate while airborne by 1 to 360 degrees clockwise or counterclockwise."""
    if not 1 <= angle_deg <= 360:
        raise ToolError("angle_deg must be between 1 and 360")
    return await backend_api.request(
        "POST",
        "/api/control/rotate",
        {"direction": direction.value, "angle_deg": angle_deg},
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
