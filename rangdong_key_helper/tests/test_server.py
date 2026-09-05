"""Tests for Ingress and CSRF enforcement."""

from __future__ import annotations

import asyncio
import re
from unittest.mock import AsyncMock, Mock

from aiohttp.test_utils import TestClient, TestServer
from rangdong_helper.server import create_app

INGRESS_HEADERS = {
    "X-Hass-Source": "core.ingress",
    "X-Ingress-Path": "/api/hassio_ingress/test-token",
    "X-Remote-User-Id": "admin-user",
}


def test_page_requires_ingress_and_mutation_requires_csrf() -> None:
    asyncio.run(_test_page_requires_ingress_and_mutation_requires_csrf())


async def _test_page_requires_ingress_and_mutation_requires_csrf() -> None:
    controller = Mock()
    controller.status.return_value = {
        "success": True,
        "busy": False,
        "stage": "idle",
        "last_error": None,
        "devices": [],
        "defaults": {
            "host": "192.168.1.50",
            "adb_port": 5555,
            "package_name": "com.rd.smart",
        },
    }
    controller.cleanup = AsyncMock()
    controller.clear_bridge = AsyncMock(
        return_value={"success": True, "devices": [], "message": "cleared"}
    )
    authorizer = Mock()
    authorizer.require_admin = AsyncMock()
    client = TestClient(TestServer(create_app(controller, authorizer)))
    await client.start_server()
    try:
        forbidden = await client.get("/")
        assert forbidden.status == 403

        page = await client.get("/", headers=INGRESS_HEADERS)
        assert page.status == 200
        source = await page.text()
        csrf = re.search(r"const csrfToken = \"([^\"]+)\";", source)
        assert csrf is not None

        rejected = await client.delete("/api/bridge", headers=INGRESS_HEADERS)
        assert rejected.status == 403

        accepted = await client.delete(
            "/api/bridge",
            headers={**INGRESS_HEADERS, "X-CSRF-Token": csrf.group(1)},
        )
        assert accepted.status == 200
        assert "cleared" in await accepted.text()

        controller.cloud_scan = AsyncMock(return_value={"success": True, "count": 1})
        cloud_rejected = await client.post(
            "/api/cloud/login-scan",
            headers=INGRESS_HEADERS,
            json={"username": "test@example.invalid", "password": "test-password"},
        )
        assert cloud_rejected.status == 403
        controller.cloud_scan.assert_not_called()
        cloud_accepted = await client.post(
            "/api/cloud/login-scan",
            headers={**INGRESS_HEADERS, "X-CSRF-Token": csrf.group(1)},
            json={"username": "test@example.invalid", "password": "test-password"},
        )
        assert cloud_accepted.status == 200
        assert controller.cloud_scan.call_args.args[0] == {}

        controller.upload_cloud_apk = AsyncMock(return_value={"success": True})
        upload_rejected = await client.post(
            "/api/cloud/apk/base", headers=INGRESS_HEADERS, data=b"apk"
        )
        assert upload_rejected.status == 403
        controller.upload_cloud_apk.assert_not_called()
    finally:
        await client.close()


def test_health_is_available_to_supervisor_watchdog() -> None:
    asyncio.run(_test_health_is_available_to_supervisor_watchdog())


async def _test_health_is_available_to_supervisor_watchdog() -> None:
    controller = Mock()
    controller.cleanup = AsyncMock()
    authorizer = Mock()
    authorizer.require_admin = AsyncMock()
    client = TestClient(TestServer(create_app(controller, authorizer)))
    await client.start_server()
    try:
        response = await client.get("/health")
        assert response.status == 200
        assert await response.json() == {"success": True}
    finally:
        await client.close()
