"""Tests for the authenticated transient local-key bridge registry."""

from __future__ import annotations

import asyncio
import json
import unittest

from homeassistant.exceptions import Unauthorized
from homeassistant.helpers.http import KEY_HASS
from rangdong_smart.const import DOMAIN
from rangdong_smart.key_bridge import (
    RangDongKeyBridgeView,
    clear_key_bridge_records,
    get_key_bridge_records,
    merge_key_bridge_records,
    public_key_bridge_records,
    remove_key_bridge_record,
)
from rangdong_smart.key_sources import LocalKeyRecord


class FakeHass:
    """Minimal Home Assistant-shaped object for registry tests."""

    def __init__(self) -> None:
        self.data = {}


class FakeContent:
    """Provide an aiohttp-like request body reader."""

    def __init__(self, body: bytes) -> None:
        self.body = body

    async def read(self, _limit: int = -1) -> bytes:
        """Return the configured request body."""

        return self.body


class FakeRequest(dict):
    """Minimal authenticated request for the bridge view."""

    def __init__(self, hass: FakeHass, body: bytes = b"", *, is_admin: bool = True):
        super().__init__(hass_user=type("User", (), {"is_admin": is_admin})())
        self.app = {KEY_HASS: hass}
        self.content = FakeContent(body)
        self.query = {}


class KeyBridgeTests(unittest.TestCase):
    """Verify transient storage and redacted metadata."""

    def test_records_are_listed_without_raw_keys(self) -> None:
        hass = FakeHass()
        local_key = "0123456789abcdef"
        merge_key_bridge_records(
            hass,
            {
                "device-1": LocalKeyRecord(
                    device_id="device-1",
                    local_key=local_key,
                    name="Living room",
                    host="192.168.1.20",
                )
            },
        )

        metadata = public_key_bridge_records(hass)

        self.assertNotIn(DOMAIN, hass.data)
        self.assertEqual(metadata[0]["device_id"], "device-1")
        self.assertEqual(metadata[0]["local_key"], "0123…cdef")
        self.assertNotIn(local_key, repr(metadata))

    def test_post_imports_records_and_redacts_response(self) -> None:
        hass = FakeHass()
        body = json.dumps(
            {
                "devices": [
                    {
                        "devId": "device-1",
                        "localKey": "0123456789abcdef",
                        "name": "Living room",
                        "ip": "192.168.1.20",
                    }
                ]
            }
        ).encode()

        response = asyncio.run(RangDongKeyBridgeView().post(FakeRequest(hass, body)))
        payload = json.loads(response.body)

        self.assertEqual(response.status, 200)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["devices"][0]["device_id"], "device-1")
        self.assertNotIn("0123456789abcdef", response.text)
        self.assertEqual(get_key_bridge_records(hass)["device-1"].local_key, "0123456789abcdef")

    def test_non_admin_cannot_read_bridge_metadata(self) -> None:
        hass = FakeHass()

        with self.assertRaises(Unauthorized):
            asyncio.run(
                RangDongKeyBridgeView().get(
                    FakeRequest(hass, is_admin=False),
                )
            )

    def test_records_can_be_consumed_or_cleared(self) -> None:
        hass = FakeHass()
        records = {
            "device-1": LocalKeyRecord("device-1", "0123456789abcdef"),
            "device-2": LocalKeyRecord("device-2", "fedcba9876543210"),
        }
        merge_key_bridge_records(hass, records)

        remove_key_bridge_record(hass, "device-1")
        self.assertEqual(set(get_key_bridge_records(hass)), {"device-2"})

        clear_key_bridge_records(hass)
        self.assertEqual(get_key_bridge_records(hass), {})


if __name__ == "__main__":
    unittest.main()
