"""Regression tests for QR config-flow behavior."""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from rangdong_smart.config_flow import RangDongConfigFlow
from rangdong_smart.const import (
    CONF_ACCESS_ID,
    CONF_ACCESS_SECRET,
    CONF_BRIDGE_REFRESH,
    CONF_CLOUD_REGION,
    CONF_KEY_EXPORT,
    CONF_LOCAL_KEY_SOURCE,
    LOCAL_KEY_SOURCE_ANDROID_BRIDGE,
    LOCAL_KEY_SOURCE_EXISTING_CLOUD,
    LOCAL_KEY_SOURCE_JSON,
    LOCAL_KEY_SOURCE_TUYA_CLOUD,
)
from rangdong_smart.key_bridge import merge_key_bridge_records
from rangdong_smart.key_sources import LocalKeyRecord, RangDongCloudKeyError
from rangdong_smart.local import DiscoveredLocalDevice, LocalProbeResult


class FakeHTTP:
    """Collect HTTP views registered by a config flow."""

    def __init__(self) -> None:
        self.views = []

    def register_view(self, view) -> None:
        """Record one registered view."""

        self.views.append(view)


class FakeHass:
    """Run executor jobs synchronously for unit tests."""

    def __init__(self) -> None:
        self.data = {}
        self.http = FakeHTTP()

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
            result = asyncio.run(flow.async_step_user({"connection_type": "local"}))

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

    def test_cloud_source_opens_one_time_credentials_form(self) -> None:
        flow = RangDongConfigFlow()
        flow.hass = FakeHass()
        flow.context = {"source": "user"}

        result = asyncio.run(
            flow.async_step_local_device(
                {
                    "name": "Rạng Đông phòng khách",
                    "host": "192.168.1.20",
                    "device_id": "device-1",
                    "protocol_version": "auto",
                    CONF_LOCAL_KEY_SOURCE: LOCAL_KEY_SOURCE_TUYA_CLOUD,
                }
            )
        )

        self.assertEqual(result["step_id"], "local_key_cloud")
        self.assertEqual(flow._local_device_id, "device-1")
        self.assertEqual(flow._local_host, "192.168.1.20")

    def test_cloud_import_does_not_persist_project_credentials(self) -> None:
        flow = RangDongConfigFlow()
        flow.hass = FakeHass()
        flow.context = {"source": "user"}
        flow._local_device_id = "device-1"
        flow._local_host = "192.168.1.20"
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = lambda: None
        record = LocalKeyRecord(
            device_id="device-1",
            local_key="0123456789abcdef",
            name="Imported lamp",
            product_id="product-1",
        )

        with patch(
            "rangdong_smart.config_flow.fetch_tuya_cloud_devices",
            return_value={"device-1": record},
        ):
            result = asyncio.run(
                flow.async_step_local_key_cloud(
                    {
                        "device_id": "device-1",
                        CONF_ACCESS_ID: "project-access-id",
                        CONF_ACCESS_SECRET: "project-access-secret",
                        CONF_CLOUD_REGION: "sg",
                    }
                )
            )

        self.assertEqual(result["step_id"], "local_key_confirm")
        self.assertNotIn("project-access-secret", repr(result))

        with patch(
            "rangdong_smart.config_flow.probe_local_device",
            return_value=LocalProbeResult("3.5", {"1": True}),
        ):
            final = asyncio.run(
                flow.async_step_local_key_confirm(
                    {
                        "name": "Imported lamp",
                        "host": "192.168.1.20",
                        "device_id": "device-1",
                        "protocol_version": "auto",
                    }
                )
            )

        self.assertEqual(final["type"], "create_entry")
        self.assertEqual(final["data"]["local_key"], "0123456789abcdef")
        self.assertNotIn(CONF_ACCESS_ID, final["data"])
        self.assertNotIn(CONF_ACCESS_SECRET, final["data"])
        self.assertNotIn(CONF_CLOUD_REGION, final["data"])

    def test_cloud_error_does_not_echo_access_secret(self) -> None:
        flow = RangDongConfigFlow()
        flow.hass = FakeHass()
        flow.context = {"source": "user"}

        with patch(
            "rangdong_smart.config_flow.fetch_tuya_cloud_devices",
            side_effect=RangDongCloudKeyError("rejected"),
        ):
            result = asyncio.run(
                flow.async_step_local_key_cloud(
                    {
                        "device_id": "device-1",
                        CONF_ACCESS_ID: "project-access-id",
                        CONF_ACCESS_SECRET: "do-not-echo-this-secret",
                        CONF_CLOUD_REGION: "sg",
                    }
                )
            )

        self.assertEqual(result["errors"]["base"], "cloud_key_error")
        self.assertNotIn("do-not-echo-this-secret", repr(result))

    def test_json_import_payload_is_not_persisted(self) -> None:
        flow = RangDongConfigFlow()
        flow.hass = FakeHass()
        flow.context = {"source": "user"}
        flow._local_device_id = "device-1"
        flow._local_host = "192.168.1.20"
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = lambda: None
        payload = '[{"id":"device-1","key":"abcdefghijklmnop"}]'

        result = asyncio.run(
            flow.async_step_local_key_json(
                {
                    "device_id": "device-1",
                    CONF_KEY_EXPORT: payload,
                }
            )
        )
        self.assertEqual(result["step_id"], "local_key_confirm")
        self.assertNotIn(payload, repr(result))

        with patch(
            "rangdong_smart.config_flow.probe_local_device",
            return_value=LocalProbeResult("3.4", {"1": False}),
        ):
            final = asyncio.run(
                flow.async_step_local_key_confirm(
                    {
                        "name": "JSON lamp",
                        "host": "192.168.1.20",
                        "device_id": "device-1",
                        "protocol_version": "auto",
                    }
                )
            )

        self.assertEqual(final["data"]["local_key"], "abcdefghijklmnop")
        self.assertNotIn(CONF_KEY_EXPORT, final["data"])

    def test_existing_cloud_entry_can_supply_local_key(self) -> None:
        flow = RangDongConfigFlow()
        flow.hass = FakeHass()
        flow.context = {"source": "user"}
        cloud_device = SimpleNamespace(
            id="device-1",
            local_key="fedcba9876543210",
            name="Cloud lamp",
            product_id="product-1",
        )
        manager = SimpleNamespace(device_map={"device-1": cloud_device})
        flow.hass.data["rangdong_smart"] = {
            "cloud-entry": SimpleNamespace(manager=manager)
        }

        result = asyncio.run(
            flow.async_step_local_device(
                {
                    "name": "Cloud lamp",
                    "host": "192.168.1.20",
                    "device_id": "device-1",
                    "protocol_version": "auto",
                    CONF_LOCAL_KEY_SOURCE: LOCAL_KEY_SOURCE_EXISTING_CLOUD,
                }
            )
        )

        self.assertEqual(result["step_id"], "local_key_confirm")
        self.assertNotIn("fedcba9876543210", repr(result))

    def test_json_source_opens_import_form_without_manual_key(self) -> None:
        flow = RangDongConfigFlow()
        flow.hass = FakeHass()
        flow.context = {"source": "user"}

        result = asyncio.run(
            flow.async_step_local_device(
                {
                    "name": "Rạng Đông Local",
                    "host": "192.168.1.20",
                    "device_id": "device-1",
                    "protocol_version": "auto",
                    CONF_LOCAL_KEY_SOURCE: LOCAL_KEY_SOURCE_JSON,
                }
            )
        )

        self.assertEqual(result["step_id"], "local_key_json")

    def test_android_bridge_source_lists_matching_key(self) -> None:
        flow = RangDongConfigFlow()
        flow.hass = FakeHass()
        flow.context = {"source": "user"}
        local_key = "abcdefghijklmnop"
        merge_key_bridge_records(
            flow.hass,
            {
                "device-1": LocalKeyRecord(
                    device_id="device-1",
                    local_key=local_key,
                    host="192.168.1.20",
                    name="Bridge lamp",
                )
            },
        )

        result = asyncio.run(
            flow.async_step_local_device(
                {
                    "name": "Bridge lamp",
                    "host": "192.168.1.20",
                    "device_id": "device-1",
                    "protocol_version": "auto",
                    CONF_LOCAL_KEY_SOURCE: LOCAL_KEY_SOURCE_ANDROID_BRIDGE,
                }
            )
        )

        self.assertEqual(result["step_id"], "local_key_confirm")
        self.assertNotIn(local_key, repr(result))

    def test_android_bridge_source_requests_refresh_when_empty(self) -> None:
        flow = RangDongConfigFlow()
        flow.hass = FakeHass()
        flow.context = {"source": "user"}

        result = asyncio.run(
            flow.async_step_local_device(
                {
                    "name": "Rạng Đông Local",
                    "host": "192.168.1.20",
                    "device_id": "device-1",
                    "protocol_version": "auto",
                    CONF_LOCAL_KEY_SOURCE: LOCAL_KEY_SOURCE_ANDROID_BRIDGE,
                }
            )
        )

        self.assertEqual(result["step_id"], "local_key_bridge")
        schema_keys = {key.schema for key in result["data_schema"].schema}
        self.assertIn(CONF_BRIDGE_REFRESH, schema_keys)
        self.assertEqual(len(flow.hass.http.views), 1)

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
