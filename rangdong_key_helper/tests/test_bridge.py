"""Tests for integration bridge activation and redacted imports."""

from __future__ import annotations

import asyncio

from aiohttp import web
from aiohttp.test_utils import TestServer
from rangdong_helper.bridge import HomeAssistantBridge
from rangdong_helper.validation import LocalKeyRecord


def test_import_activates_integration_then_retries_bridge() -> None:
    asyncio.run(_test_import_activates_integration_then_retries_bridge())


async def _test_import_activates_integration_then_retries_bridge() -> None:
    state = {"active": False, "flow_deleted": False, "authorization": ""}

    async def bridge(request: web.Request) -> web.Response:
        state["authorization"] = request.headers.get("Authorization", "")
        if not state["active"]:
            raise web.HTTPNotFound
        payload = await request.json()
        assert payload["devices"][0]["localKey"] == "0123456789abcdef"
        return web.json_response(
            {
                "success": True,
                "count": 1,
                "available_count": 1,
                "devices": [{"device_id": "device-1", "local_key": "0123…cdef"}],
            }
        )

    async def create_flow(request: web.Request) -> web.Response:
        assert await request.json() == {"handler": "rangdong_smart"}
        state["active"] = True
        return web.json_response({"type": "form", "flow_id": "temporary-flow"})

    async def delete_flow(_request: web.Request) -> web.Response:
        state["flow_deleted"] = True
        return web.json_response({"message": "Flow aborted"})

    app = web.Application()
    app.router.add_post("/bridge", bridge)
    app.router.add_post("/flow", create_flow)
    app.router.add_delete("/flow/temporary-flow", delete_flow)
    server = TestServer(app)
    await server.start_server()
    try:
        client = HomeAssistantBridge(
            token="supervisor-test-token",
            url=str(server.make_url("/bridge")),
            flow_url=str(server.make_url("/flow")),
        )
        result = await client.import_records(
            [LocalKeyRecord("device-1", "0123456789abcdef")]
        )
    finally:
        await server.close()

    assert result["devices"][0]["local_key"] == "0123…cdef"
    assert state["flow_deleted"] is True
    assert state["authorization"] == "Bearer supervisor-test-token"
