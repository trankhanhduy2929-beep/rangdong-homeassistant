"""Add-on enforcement must not leak keys or invoke cloud when denied."""

import asyncio
import re
import time
from unittest.mock import AsyncMock, Mock, patch

from aiohttp.test_utils import TestClient, TestServer
from rangdong_helper.errors import HelperError
from rangdong_helper.licensing import AddonLicense
from rangdong_helper.server import create_app

HEADERS = {
    "X-Hass-Source": "core.ingress",
    "X-Ingress-Path": "/api/hassio_ingress/test",
    "X-Remote-User-Id": "admin",
}


def test_addon_identity_is_stable_and_private(tmp_path):
    client = AddonLicense(identity_path=tmp_path / "identity")
    first = client._read_identity()
    assert client._read_identity() == first
    assert (tmp_path / "identity").stat().st_mode & 0o777 == 0o600


def test_enforced_addon_rejects_mismatched_compatibility_core():
    async def exercise():
        client = AddonLicense()
        with (
            patch.object(
                client,
                "status",
                AsyncMock(return_value={"valid": True, "enforced": False}),
            ),
            patch("rangdong_helper.licensing.license_config.ENFORCE", True),
        ):
            try:
                await client.require_valid()
            except HelperError as error:
                assert error.code == "license_required"
            else:
                raise AssertionError("Must reject incompatible license settings")

    asyncio.run(exercise())


def test_denied_license_blocks_cloud_but_not_cleanup_and_removed_routes():
    async def exercise():
        helper = Mock()
        helper.status.return_value = {"defaults": {}}
        helper.cloud_scan = AsyncMock()
        helper.clear_bridge = AsyncMock(return_value={"success": True})
        helper.cleanup = AsyncMock()
        license_client = Mock()
        license_client.require_valid = AsyncMock(
            side_effect=HelperError("license_required", "License required", status=403)
        )
        license_client.status = AsyncMock(
            return_value={"success": True, "valid": False}
        )
        auth = Mock()
        auth.require_admin = AsyncMock()
        client = TestClient(TestServer(create_app(helper, auth, license_client)))
        await client.start_server()
        try:
            page = await client.get("/", headers=HEADERS)
            source = await page.text()
            csrf = re.search(r'const csrfToken = "([^"]+)";', source).group(1)
            assert 'type="file"' not in source
            assert "Frida" not in source
            headers = {**HEADERS, "X-CSRF-Token": csrf}
            response = await client.post(
                "/api/cloud/login-scan",
                headers=headers,
                json={"username": "test@example.invalid", "password": "private-test"},
            )
            assert response.status == 403
            helper.cloud_scan.assert_not_called()
            denied_status = await client.get("/api/status", headers=HEADERS)
            assert denied_status.status == 403
            assert "private-test" not in await response.text()
            assert (await client.delete("/api/bridge", headers=headers)).status == 200
            for path in ("pair", "prepare", "scan", "login-scan", "cloud/apk/base"):
                assert (
                    await client.post(f"/api/{path}", headers=headers, json={})
                ).status == 404
            assert (
                await client.post(
                    "/api/license", headers=HEADERS, json={"key": "test-license-key"}
                )
            ).status == 403
        finally:
            await client.close()

    asyncio.run(exercise())


def test_expired_or_offline_confirmation_cannot_unlock_addon(tmp_path):
    async def exercise():
        bridge = Mock()
        bridge.license_request = AsyncMock()
        client = AddonLicense(bridge=bridge, identity_path=tmp_path / "identity")
        with patch("rangdong_helper.licensing.license_config.ENFORCE", True):
            for response in [
                {
                    "valid": True,
                    "enforced": True,
                    "status": "active",
                    "expires_at": time.time() - 1,
                },
                {
                    "valid": True,
                    "enforced": True,
                    "status": "offline_grace",
                    "expires_at": time.time() + 60,
                },
                {"valid": True, "enforced": True, "status": "active"},
                {
                    "valid": True,
                    "enforced": False,
                    "status": "active",
                    "expires_at": time.time() + 60,
                },
            ]:
                bridge.license_request.return_value = response
                assert (await client.status())["valid"] is False
            bridge.license_request.return_value = {
                "valid": True,
                "enforced": True,
                "status": "active",
                "expires_at": time.time() + 60,
            }
            await client.require_valid()

    asyncio.run(exercise())


def test_expiry_during_collection_does_not_return_keys():
    async def exercise():
        helper = Mock()
        helper.status.return_value = {"defaults": {}}
        helper.cloud_scan = AsyncMock(
            return_value={
                "success": True,
                "devices": [{"local_key": "0123456789abcdef"}],
            }
        )
        helper.clear_bridge = AsyncMock(return_value={"success": True})
        helper.cleanup = AsyncMock()
        licensing = Mock()
        licensing.require_valid = AsyncMock(
            side_effect=[None, HelperError("license_required", "Expired", status=403)]
        )
        auth = Mock()
        auth.require_admin = AsyncMock()
        client = TestClient(TestServer(create_app(helper, auth, licensing)))
        await client.start_server()
        try:
            page = await client.get("/", headers=HEADERS)
            csrf = re.search(r'const csrfToken = "([^"]+)";', await page.text()).group(
                1
            )
            response = await client.post(
                "/api/cloud/login-scan",
                headers={**HEADERS, "X-CSRF-Token": csrf},
                json={"username": "test@example.invalid", "password": "test-password"},
            )
            assert response.status == 403
            assert "0123456789abcdef" not in await response.text()
            helper.clear_bridge.assert_awaited_once()
        finally:
            await client.close()

    asyncio.run(exercise())
