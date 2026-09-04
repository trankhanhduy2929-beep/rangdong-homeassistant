"""Tests for secure orchestration and cleanup."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from rangdong_helper.controller import AddonOptions, HelperController
from rangdong_helper.errors import HelperError
from rangdong_helper.installer import FridaServerBinary
from rangdong_helper.validation import AndroidTarget, LoginCredentials


def _controller() -> tuple[
    HelperController, AsyncMock, AsyncMock, AsyncMock, AsyncMock
]:
    adb = AsyncMock()
    adb.connect.return_value = "192.168.1.50:5555"
    adb.get_abi.return_value = "arm64-v8a"
    adb.start_app.return_value = 1234
    installer = AsyncMock()
    installer.get_server.return_value = FridaServerBinary(
        Path("/tmp/frida-server"),
        "0" * 64,
    )
    frida = AsyncMock()
    frida.probe.return_value = {"ok": True}
    frida.collect.return_value = [
        {
            "device_id": "device-1",
            "local_key": "0123456789abcdef",
            "name": "Lamp",
            "host": "192.168.1.90",
            "protocol_version": "3.4",
        }
    ]
    bridge = AsyncMock()
    bridge.import_records.return_value = {"success": True, "available_count": 1}
    controller = HelperController(
        options=AddonOptions("192.168.1.50", 5555, "com.rd.smart"),
        adb=adb,
        installer=installer,
        frida_client=frida,
        bridge=bridge,
    )
    return controller, adb, installer, frida, bridge


def test_scan_imports_records_but_returns_only_masked_key() -> None:
    asyncio.run(_test_scan_imports_records_but_returns_only_masked_key())


async def _test_scan_imports_records_but_returns_only_masked_key() -> None:
    controller, adb, _installer, frida, bridge = _controller()
    credentials = LoginCredentials("84", "900000000", "temporary-password")
    imported_records = []

    async def capture_records(records):
        imported_records.extend(records)
        return {"success": True, "available_count": len(records)}

    bridge.import_records.side_effect = capture_records

    result = await controller.scan(
        AndroidTarget("192.168.1.50", 5555, "com.rd.smart"),
        credentials,
    )

    assert result["devices"][0]["local_key"] == "0123…cdef"
    assert "0123456789abcdef" not in repr(result)
    frida.collect.assert_awaited_once_with(1234, credentials)
    assert imported_records[0].device_id == "device-1"
    adb.remove_forward.assert_awaited_once()
    adb.stop_frida_server.assert_awaited_once()


def test_prepare_failure_still_closes_frida() -> None:
    asyncio.run(_test_prepare_failure_still_closes_frida())


async def _test_prepare_failure_still_closes_frida() -> None:
    controller, adb, _installer, frida, _bridge = _controller()
    frida.probe.side_effect = HelperError("probe_failed", "probe failed")

    with pytest.raises(HelperError, match="probe failed"):
        await controller.prepare(AndroidTarget("192.168.1.50", 5555, "com.rd.smart"))

    adb.remove_forward.assert_awaited_once_with("192.168.1.50:5555")
    adb.stop_frida_server.assert_awaited_once_with("192.168.1.50:5555")
