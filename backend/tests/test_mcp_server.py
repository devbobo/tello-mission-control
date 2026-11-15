import json
import os
import sys

import httpx
import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.server.fastmcp.exceptions import ToolError

from app import mcp_server
from app.mcp_server import BackendApi, MoveDirection, RotateDirection


@pytest.mark.asyncio
async def test_backend_api_sends_existing_control_request():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/control/move"
        assert json.loads(request.content) == {
            "direction": "forward",
            "distance_cm": 100,
        }
        return httpx.Response(200, json={"ok": True, "message": "Moved forward 100cm"})

    client = BackendApi(
        "http://backend",
        transport=httpx.MockTransport(handler),
    )

    response = await client.request(
        "POST",
        "/api/control/move",
        {"direction": "forward", "distance_cm": 100},
    )

    assert json.loads(response)["ok"] is True


@pytest.mark.asyncio
async def test_backend_api_surfaces_http_errors():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "Drone is not flying"})

    client = BackendApi("http://backend", transport=httpx.MockTransport(handler))

    with pytest.raises(ToolError, match="HTTP 409:.*Drone is not flying"):
        await client.request("POST", "/api/control/move")


@pytest.mark.asyncio
async def test_backend_api_surfaces_connection_errors():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    client = BackendApi("http://backend", transport=httpx.MockTransport(handler))

    with pytest.raises(ToolError, match="Could not reach the Tello backend"):
        await client.request("GET", "/api/status")


@pytest.mark.asyncio
async def test_move_and_rotate_validate_limits_before_request(monkeypatch):
    class UnexpectedRequest:
        async def request(self, *args, **kwargs):
            pytest.fail("Invalid tool arguments must not reach the backend")

    monkeypatch.setattr(mcp_server, "backend_api", UnexpectedRequest())

    with pytest.raises(ToolError, match="distance_cm must be between 20 and 500"):
        await mcp_server.move(MoveDirection.forward, 19)
    with pytest.raises(ToolError, match="angle_deg must be between 1 and 360"):
        await mcp_server.rotate(RotateDirection.cw, 361)


@pytest.mark.asyncio
async def test_move_and_rotate_forward_typed_payloads(monkeypatch):
    class CaptureRequest:
        def __init__(self):
            self.calls = []

        async def request(self, method, path, payload=None):
            self.calls.append((method, path, payload))
            return '{"ok": true}'

    client = CaptureRequest()
    monkeypatch.setattr(mcp_server, "backend_api", client)

    await mcp_server.move(MoveDirection.forward, 100)
    await mcp_server.rotate(RotateDirection.ccw, 90)

    assert client.calls == [
        ("POST", "/api/control/move", {"direction": "forward", "distance_cm": 100}),
        ("POST", "/api/control/rotate", {"direction": "ccw", "angle_deg": 90}),
    ]


@pytest.mark.asyncio
async def test_stdio_server_advertises_and_validates_tools():
    env = os.environ.copy()
    env["TELLO_MCP_API_URL"] = "http://127.0.0.1:1"
    env["TELLO_MCP_REQUEST_TIMEOUT"] = "0.5"
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_server"],
        env=env,
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.list_tools()
            invalid_range = await session.call_tool(
                "move",
                {"direction": "forward", "distance_cm": 501},
            )
            invalid_direction = await session.call_tool(
                "move",
                {"direction": "diagonal", "distance_cm": 100},
            )
            backend_unavailable = await session.call_tool("get_drone_status")

    tools = {tool.name: tool for tool in result.tools}
    assert set(tools) == {
        "get_drone_status",
        "connect_drone",
        "disconnect_drone",
        "takeoff",
        "land",
        "emergency_stop",
        "move",
        "rotate",
    }
    assert tools["move"].inputSchema["$defs"]["MoveDirection"]["enum"] == [
        "forward",
        "back",
        "left",
        "right",
        "up",
        "down",
    ]
    assert tools["move"].inputSchema["properties"]["distance_cm"]["type"] == "integer"
    assert tools["rotate"].inputSchema["$defs"]["RotateDirection"]["enum"] == [
        "cw",
        "ccw",
    ]
    assert tools["rotate"].inputSchema["properties"]["angle_deg"]["type"] == "integer"
    assert invalid_range.isError is True
    assert "distance_cm must be between 20 and 500" in invalid_range.content[0].text
    assert invalid_direction.isError is True
    assert backend_unavailable.isError is True
    assert "Could not reach the Tello backend" in backend_unavailable.content[0].text
