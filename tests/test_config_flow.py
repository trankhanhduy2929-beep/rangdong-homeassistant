"""Regression tests for QR config-flow behavior."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from rangdong_smart.config_flow import RangDongConfigFlow
from rangdong_smart.local import DiscoveredLocalDevice, LocalProbeResult


class FakeHass:
    """Run executor jobs synchronously for unit tests."""

    async def async_add_executor_job(self, target, *args):
        """Call an executor target without creating a thread."""

        return target(*args)


class FakeLoginControl:
    """Return predefined QR and login responses."""

    def __init__(self, qr_responses, login_response):
        self.qr_responses = list(qr_responses)
        self.login_response = login_response

    def qr_code(self, _client_id, _schema, _user_code):
        """Return the next QR response."""

        return self.qr_responses.pop(0)

    def login_result(self, _token, _client_id, _user_code):
        """Return the configured login response."""

        return self.login_response


class ConfigFlowTests(unittest.TestCase):
    """Verify QR refresh and invalid-response handling."""

    def _flow(self, login_control: FakeLoginControl) -> RangDongConfigFlow:
        flow = RangDongConfigFlow()
        flow.hass = FakeHass()
        flow.context = {"source": "user"}
        flow._login_control = login_control
        flow._user_code = "UserCodeABC"
        flow._qr_token = "old-token"
        return flow

    def test_failed_scan_replaces_qr_token(self) -> None:
        flow = self._flow(
            FakeLoginControl(
                [
                    {
                        "success": True,
                        "result": {"qrcode": "new-token"},
                    }
                ],
                (False, {"code": "E0020003", "msg": "Login failed"}),
            )
        )

        result = asyncio.run(flow.async_step_scan({"qr": None}))
        qr_selector = next(iter(result["data_schema"].schema.values()))

        self.assertEqual(result["step_id"], "scan")
        self.assertEqual(result["errors"]["base"], "designated_app_error")
        self.assertEqual(
            qr_selector.config["data"],
            "tuyaSmart--qrLogin?token=new-token",
        )

    def test_failed_refresh_returns_to_user_code(self) -> None:
        flow = self._flow(
            FakeLoginControl(
                [
                    {
                        "success": False,
                        "code": "NETWORK_ERROR",
                        "msg": "Gateway unavailable",
                    }
                ],
                (False, {"code": "E0020003", "msg": "Login failed"}),
            )
        )

        result = asyncio.run(flow.async_step_scan({"qr": None}))

        self.assertEqual(result["step_id"], "cloud_qr")
        self.assertEqual(result["errors"]["base"], "login_error")
        self.assertEqual(flow._qr_token, "")

    def test_non_mapping_qr_response_is_rejected(self) -> None:
        flow = self._flow(FakeLoginControl([[]], (False, {})))

        success, response = asyncio.run(flow._async_get_qr_code("UserCodeABC"))

        self.assertFalse(success)
        self.assertEqual(response["code"], "INVALID_RESPONSE")
        self.assertEqual(flow._qr_token, "")

    def test_empty_user_code_clears_previous_qr_token(self) -> None:
        flow = self._flow(FakeLoginControl([], (False, {})))

        success, response = asyncio.run(flow._async_get_qr_code("   "))

        self.assertFalse(success)
        self.assertEqual(response["code"], "USERCODE_EMPTY")
        self.assertEqual(flow._qr_token, "")

    def test_user_step_defaults_to_local_connection(self) -> None:
        flow = RangDongConfigFlow()
        flow.context = {"source": "user"}

        result = asyncio.run(flow.async_step_user())

        self.assertEqual(result["step_id"], "user")
        field = next(iter(result["data_schema"].schema))
        self.assertEqual(field.schema, "connection_type")
        self.assertEqual(field.default(), "local")

    def test_local_scan_prefills_discovered_device(self) -> None:
        flow = RangDongConfigFlow()
        flow.hass = FakeHass()
        flow.context = {"source": "user"}
        discovered = DiscoveredLocalDevice(
            device_id="device-1",
            host="192.168.1.20",
            product_id="product-1",
            protocol_version="3.5",
            name="Living room",
        )

        with patch(
            "rangdong_smart.config_flow.scan_lan_devices",
            return_value={"device-1": discovered},
        ):
            result = asyncio.run(
                flow.async_step_user({"connection_type": "local"})
            )

        self.assertEqual(result["step_id"], "local_scan")
        next_result = asyncio.run(
            flow.async_step_local_scan({"discovered_device": "device-1"})
        )
        self.assertEqual(next_result["step_id"], "local_device")
        self.assertEqual(flow._local_device_id, "device-1")
        self.assertEqual(flow._local_host, "192.168.1.20")
        self.assertEqual(flow._local_protocol_version, "3.5")

    def test_local_device_success_creates_local_entry(self) -> None:
        flow = RangDongConfigFlow()
        flow.hass = FakeHass()
        flow.context = {"source": "user"}
        flow._local_product_id = "product-1"
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = lambda: None
        local_key = "x" * 16

        with patch(
            "rangdong_smart.config_flow.probe_local_device",
            return_value=LocalProbeResult("3.5", {"1": True}),
        ):
            result = asyncio.run(
                flow.async_step_local_device(
                    {
                        "name": "Rạng Đông phòng khách",
                        "host": "192.168.1.20",
                        "device_id": "device-1",
                        "local_key": local_key,
                        "protocol_version": "auto",
                    }
                )
            )

        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["connection_type"], "local")
        self.assertEqual(result["data"]["protocol_version"], "3.5")
        self.assertEqual(result["data"]["local_key"], local_key)
        flow.async_set_unique_id.assert_awaited_once_with("local:device-1")

    def test_reconfigure_local_updates_existing_entry(self) -> None:
        flow = RangDongConfigFlow()
        flow.hass = FakeHass()
        flow.context = {"source": "reconfigure"}
        flow._local_product_id = "product-1"
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_mismatch = MagicMock()
        entry = SimpleNamespace(entry_id="entry-1", unique_id="local:device-1")
        flow._get_reconfigure_entry = MagicMock(return_value=entry)
        flow.async_update_reload_and_abort = MagicMock(
            return_value={"type": "abort", "reason": "reconfigure_successful"}
        )
        local_key = "y" * 16

        with patch(
            "rangdong_smart.config_flow.probe_local_device",
            return_value=LocalProbeResult("3.4", {"1": False}),
        ):
            result = asyncio.run(
                flow.async_step_reconfigure_local(
                    {
                        "name": "Rạng Đông phòng ngủ",
                        "host": "192.168.1.30",
                        "device_id": "device-1",
                        "local_key": local_key,
                        "protocol_version": "auto",
                    }
                )
            )

        self.assertEqual(result["reason"], "reconfigure_successful")
        flow.async_set_unique_id.assert_awaited_once_with("local:device-1")
        flow._abort_if_unique_id_mismatch.assert_called_once_with()
        updated_data = flow.async_update_reload_and_abort.call_args.kwargs["data"]
        self.assertEqual(updated_data["host"], "192.168.1.30")
        self.assertEqual(updated_data["local_key"], local_key)
        self.assertEqual(updated_data["protocol_version"], "3.4")


if __name__ == "__main__":
    unittest.main()
