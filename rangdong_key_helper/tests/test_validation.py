"""Tests for untrusted helper input and redacted device output."""

from __future__ import annotations

import pytest
from rangdong_helper.errors import HelperError
from rangdong_helper.validation import (
    mask_local_key,
    normalize_host,
    parse_login,
    parse_target,
    validate_records,
)


def test_target_requires_private_ip_and_formats_serial() -> None:
    target = parse_target(
        {
            "host": "192.168.20.15",
            "adb_port": 37123,
            "package_name": "com.rd.smart",
        }
    )

    assert target.serial == "192.168.20.15:37123"

    with pytest.raises(HelperError, match="mạng LAN"):
        normalize_host("8.8.8.8")
    with pytest.raises(HelperError, match="không dùng hostname"):
        normalize_host("phone.local")


@pytest.mark.parametrize(
    ("raw_phone", "expected"),
    [
        ("0912 345 678", "912345678"),
        ("+84 912345678", "912345678"),
        ("0084912345678", "912345678"),
    ],
)
def test_login_normalizes_vietnam_phone(raw_phone: str, expected: str) -> None:
    credentials = parse_login(
        {
            "country_code": "+84",
            "phone": raw_phone,
            "password": "not-a-real-password",
        }
    )

    assert credentials.country_code == "84"
    assert credentials.phone == expected


def test_records_keep_only_valid_keys_and_private_metadata() -> None:
    records = validate_records(
        [
            {
                "device_id": "valid-device-1",
                "local_key": "0123456789abcdef",
                "name": "Living room",
                "host": "192.168.1.20",
                "product_id": "product-a",
                "protocol_version": "3.5",
            },
            {
                "device_id": "invalid-key",
                "local_key": "short",
            },
            {
                "device_id": "valid-device-1",
                "local_key": "fedcba9876543210",
                "host": "8.8.8.8",
            },
        ]
    )

    assert len(records) == 1
    assert records[0].local_key == "fedcba9876543210"
    assert records[0].host is None
    assert records[0].masked()["local_key"] == "fedc…3210"
    assert "fedcba9876543210" not in repr(records[0].masked())
    assert mask_local_key("short") == "<redacted>"
