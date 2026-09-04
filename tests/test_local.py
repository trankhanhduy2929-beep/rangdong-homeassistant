"""Tests for LAN discovery normalization and protocol selection."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

LOCAL_PATH = (
    Path(__file__).parents[1] / "custom_components" / "rangdong_smart" / "local.py"
)
SPEC = importlib.util.spec_from_file_location("rangdong_smart_local_test", LOCAL_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load local.py")
LOCAL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = LOCAL
SPEC.loader.exec_module(LOCAL)


class LocalHelpersTests(unittest.TestCase):
    """Verify local helper behavior without opening network sockets."""

    def test_normalize_discovery_result(self) -> None:
        devices = LOCAL.normalize_discovery_results(
            {
                "192.168.1.25": {
                    "gwId": "device-1",
                    "productKey": "product-1",
                    "version": 3.5,
                }
            }
        )

        device = devices["device-1"]
        self.assertEqual(device.host, "192.168.1.25")
        self.assertEqual(device.product_id, "product-1")
        self.assertEqual(device.protocol_version, "3.5")

    def test_public_host_is_rejected(self) -> None:
        with self.assertRaises(LOCAL.RangDongLocalHostError):
            LOCAL.normalize_local_host("8.8.8.8")

    def test_loopback_host_is_rejected(self) -> None:
        with self.assertRaises(LOCAL.RangDongLocalHostError):
            LOCAL.normalize_local_host("127.0.0.1")

    def test_client_rejects_invalid_local_key(self) -> None:
        with self.assertRaises(LOCAL.RangDongLocalAuthError):
            LOCAL.RangDongLocalClient(
                "192.168.1.20",
                "device-1",
                "too-short",
                "3.5",
            )

    def test_probe_auto_falls_back_after_constructor_error(self) -> None:
        attempted_versions: list[str] = []

        def make_device(device_id, host, local_key, version):
            del device_id, host, local_key
            attempted_versions.append(version)
            if len(attempted_versions) == 1:
                raise RuntimeError("unsupported")
            device = MagicMock()
            device.status.return_value = {"dps": {1: True}}
            return device

        with (
            patch.object(LOCAL.socket, "create_connection"),
            patch.object(
                LOCAL,
                "create_tinytuya_device",
                side_effect=make_device,
            ),
        ):
            result = LOCAL.probe_local_device(
                "192.168.1.20",
                "device-1",
                "x" * 16,
                "auto",
            )

        self.assertEqual(attempted_versions, ["3.5", "3.4"])
        self.assertEqual(result, LOCAL.LocalProbeResult("3.4", {"1": True}))

    def test_auto_protocol_tries_newest_first(self) -> None:
        self.assertEqual(
            LOCAL.protocol_candidates("auto"),
            ("3.5", "3.4", "3.3", "3.2", "3.1"),
        )

    def test_explicit_protocol_does_not_fallback(self) -> None:
        self.assertEqual(LOCAL.protocol_candidates("3.3"), ("3.3",))

    def test_response_dps_normalizes_ids(self) -> None:
        self.assertEqual(
            LOCAL.response_dps({"dps": {1: True, "2": 50}}),
            {"1": True, "2": 50},
        )
        self.assertIsNone(
            LOCAL.response_dps({"Error": "bad key", "Err": "914"})
        )


if __name__ == "__main__":
    unittest.main()
