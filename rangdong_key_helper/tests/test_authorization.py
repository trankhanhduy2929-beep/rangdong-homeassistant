"""Tests for administrator-only Ingress authorization."""

from __future__ import annotations

import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from rangdong_helper.authorization import HomeAssistantUserAuthorizer
from rangdong_helper.errors import HelperError


def test_authorizer_accepts_admin_and_caches_lookup() -> None:
    asyncio.run(_test_authorizer_accepts_admin_and_caches_lookup())


async def _test_authorizer_accepts_admin_and_caches_lookup() -> None:
    connections = 0

    async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
        nonlocal connections
        connections += 1
        websocket = web.WebSocketResponse()
        await websocket.prepare(request)
        await websocket.send_json({"type": "auth_required"})
        auth = await websocket.receive_json()
        assert auth == {"type": "auth", "access_token": "test-token"}
        await websocket.send_json({"type": "auth_ok"})
        command = await websocket.receive_json()
        assert command == {"id": 1, "type": "config/auth/list"}
        await websocket.send_json(
            {
                "id": 1,
                "type": "result",
                "success": True,
                "result": [
                    {
                        "id": "admin-user",
                        "is_owner": False,
                        "group_ids": ["system-admin"],
                    }
                ],
            }
        )
        await websocket.close()
        return websocket

    app = web.Application()
    app.router.add_get("/websocket", websocket_handler)
    server = TestServer(app)
    await server.start_server()
    try:
        url = str(server.make_url("/websocket")).replace("http://", "ws://")
        authorizer = HomeAssistantUserAuthorizer(
            token="test-token",
            websocket_url=url,
        )
        await authorizer.require_admin("admin-user")
        await authorizer.require_admin("admin-user")
    finally:
        await server.close()

    assert connections == 1


def test_authorizer_rejects_non_admin() -> None:
    asyncio.run(_test_authorizer_rejects_non_admin())


async def _test_authorizer_rejects_non_admin() -> None:
    async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
        websocket = web.WebSocketResponse()
        await websocket.prepare(request)
        await websocket.send_json({"type": "auth_required"})
        await websocket.receive_json()
        await websocket.send_json({"type": "auth_ok"})
        await websocket.receive_json()
        await websocket.send_json(
            {
                "id": 1,
                "type": "result",
                "success": True,
                "result": [
                    {
                        "id": "normal-user",
                        "is_owner": False,
                        "group_ids": ["system-users"],
                    }
                ],
            }
        )
        await websocket.close()
        return websocket

    app = web.Application()
    app.router.add_get("/websocket", websocket_handler)
    server = TestServer(app)
    await server.start_server()
    try:
        url = str(server.make_url("/websocket")).replace("http://", "ws://")
        authorizer = HomeAssistantUserAuthorizer(
            token="test-token",
            websocket_url=url,
        )
        with pytest.raises(HelperError, match="quản trị viên"):
            await authorizer.require_admin("normal-user")
    finally:
        await server.close()
