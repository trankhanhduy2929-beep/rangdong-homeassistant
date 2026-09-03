"""Regression tests for QR config-flow behavior."""

from __future__ import annotations

import asyncio
import unittest

from rangdong_smart.config_flow import RangDongConfigFlow


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

        self.assertEqual(result["step_id"], "user")
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


if __name__ == "__main__":
    unittest.main()
