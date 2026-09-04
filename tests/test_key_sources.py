"""Tests for one-time local-key imports."""

from __future__ import annotations

import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from rangdong_smart.key_sources import (
    LocalKeyRecord,
    RangDongCloudKeyError,
    RangDongKeyExportError,
    fetch_tuya_cloud_devices,
    parse_local_key_export,
    records_from_existing_cloud_devices,
)


class KeySourceTests(unittest.TestCase):
    """Verify supported exports and cloud normalization."""

    def test_parse_tinytuya_devices_export(self) -> None:
        records = parse_local_key_export(
            json.dumps(
                [
                    {
                        "id": "device-1",
                        "key": "0123456789abcdef",
                        "name": "Living room",
                        "ip": "192.168.1.20",
                        "product_id": "product-1",
                        "version": 3.5,
                    }
                ]
            )
        )

        self.assertEqual(
            records["device-1"],
            LocalKeyRecord(
                device_id="device-1",
                local_key="0123456789abcdef",
                name="Living room",
                host="192.168.1.20",
                product_id="product-1",
                protocol_version="3.5",
            ),
        )

    def test_parse_mobile_api_and_device_map_exports(self) -> None:
        records = parse_local_key_export(
            {
                "result": [
                    {
                        "devId": "device-mobile",
                        "localKey": "abcdefghijklmnop",
                    }
                ],
                "devices": {
                    "device-map": {
                        "local_key": "ABCDEFGHIJKLMNOP",
                    }
                },
            }
        )

        self.assertEqual(records["device-mobile"].local_key, "abcdefghijklmnop")
        self.assertEqual(records["device-map"].local_key, "ABCDEFGHIJKLMNOP")

    def test_invalid_or_missing_keys_are_rejected(self) -> None:
        with self.assertRaises(RangDongKeyExportError):
            parse_local_key_export("not-json")
        with self.assertRaises(RangDongKeyExportError):
            parse_local_key_export([{"id": "device-1", "key": "too-short"}])

    def test_existing_cloud_objects_are_normalized(self) -> None:
        records = records_from_existing_cloud_devices(
            {
                "device-1": SimpleNamespace(
                    id="device-1",
                    local_key="fedcba9876543210",
                    name="Cloud lamp",
                    product_id="product-1",
                )
            }
        )

        self.assertEqual(records["device-1"].local_key, "fedcba9876543210")
        self.assertEqual(records["device-1"].name, "Cloud lamp")

    def test_cloud_fetch_returns_only_requested_device(self) -> None:
        calls: list[dict[str, str | None]] = []

        class FakeCloud:
            def __init__(self, **kwargs):
                calls.append(kwargs)

            def getdevices(self):
                return [
                    {
                        "id": "device-1",
                        "key": "0123456789abcdef",
                    },
                    {
                        "id": "device-2",
                        "key": "abcdefghijklmnop",
                    },
                ]

        fake_tinytuya = SimpleNamespace(Cloud=FakeCloud)
        with patch.dict(sys.modules, {"tinytuya": fake_tinytuya}):
            records = fetch_tuya_cloud_devices(
                "sg",
                "access-id",
                "access-secret",
                "device-2",
            )

        self.assertEqual(list(records), ["device-2"])
        self.assertEqual(records["device-2"].local_key, "abcdefghijklmnop")
        self.assertEqual(calls[0]["apiRegion"], "sg")
        self.assertEqual(calls[0]["apiDeviceID"], "device-2")
        self.assertNotIn("access-secret", repr(records))

    def test_cloud_error_payload_is_rejected(self) -> None:
        class FakeCloud:
            def __init__(self, **_kwargs):
                pass

            def getdevices(self):
                return {"Error": "Unable to Get Cloud Token", "Err": "911"}

        with (
            patch.dict(sys.modules, {"tinytuya": SimpleNamespace(Cloud=FakeCloud)}),
            self.assertRaises(RangDongCloudKeyError),
        ):
            fetch_tuya_cloud_devices(
                "sg",
                "access-id",
                "access-secret",
                "device-1",
            )


if __name__ == "__main__":
    unittest.main()
