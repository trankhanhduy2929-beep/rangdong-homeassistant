"""Input and local-key validation helpers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from ipaddress import IPv6Address, ip_address
from typing import Any

from .constants import DEFAULT_ADB_PORT, DEFAULT_PACKAGE_NAME
from .errors import HelperError

_PACKAGE_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+\Z")
_DEVICE_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{4,128}\Z")


@dataclass(frozen=True, slots=True)
class AndroidTarget:
    """A validated Android ADB endpoint."""

    host: str
    adb_port: int
    package_name: str

    @property
    def serial(self) -> str:
        """Return the ADB network serial."""

        try:
            address = ip_address(self.host)
        except ValueError:
            address = None
        if isinstance(address, IPv6Address):
            return f"[{self.host}]:{self.adb_port}"
        return f"{self.host}:{self.adb_port}"


@dataclass(frozen=True, slots=True)
class LoginCredentials:
    """Ephemeral Rạng Đông login values."""

    country_code: str
    phone: str
    password: str


@dataclass(frozen=True, slots=True)
class LocalKeyRecord:
    """A validated device record collected from the Android app."""

    device_id: str
    local_key: str
    name: str | None = None
    host: str | None = None
    product_id: str | None = None
    protocol_version: str | None = None

    def as_bridge_payload(self) -> dict[str, str]:
        """Return a payload accepted by the integration bridge."""

        payload = {
            "devId": self.device_id,
            "localKey": self.local_key,
        }
        optional = {
            "name": self.name,
            "ip": self.host,
            "productId": self.product_id,
            "version": self.protocol_version,
        }
        payload.update({key: value for key, value in optional.items() if value})
        return payload

    def masked(self) -> dict[str, str | None]:
        """Return metadata without exposing the complete local key."""

        return {
            "device_id": self.device_id,
            "name": self.name,
            "host": self.host,
            "product_id": self.product_id,
            "protocol_version": self.protocol_version,
            "local_key": mask_local_key(self.local_key),
        }


def parse_target(
    payload: dict[str, Any],
    *,
    default_host: str = "",
    default_port: int = DEFAULT_ADB_PORT,
    default_package: str = DEFAULT_PACKAGE_NAME,
) -> AndroidTarget:
    """Validate an Android target from an API request."""

    host = normalize_host(payload.get("host", default_host))
    port = normalize_port(payload.get("adb_port", default_port), "ADB port")
    package_name = normalize_package(payload.get("package_name", default_package))
    return AndroidTarget(host, port, package_name)


def parse_login(payload: dict[str, Any]) -> LoginCredentials:
    """Validate and normalize one-time phone login data."""

    country_code = str(payload.get("country_code") or "").strip().lstrip("+")
    if not country_code.isdigit() or not 1 <= len(country_code) <= 4:
        raise HelperError("invalid_country_code", "Mã quốc gia không hợp lệ.")

    raw_phone = str(payload.get("phone") or "").strip()
    phone = re.sub(r"[\s().-]", "", raw_phone)
    if phone.startswith("+"):
        phone = phone.removeprefix("+")
        if phone.startswith(country_code):
            phone = phone.removeprefix(country_code)
    elif phone.startswith(f"00{country_code}"):
        phone = phone.removeprefix(f"00{country_code}")
    elif phone.startswith("0"):
        phone = phone.removeprefix("0")
    if not phone.isdigit() or not 6 <= len(phone) <= 15:
        raise HelperError("invalid_phone", "Số điện thoại không hợp lệ.")

    password = payload.get("password")
    if not isinstance(password, str) or not 4 <= len(password) <= 128:
        raise HelperError("invalid_password", "Mật khẩu không hợp lệ.")
    return LoginCredentials(country_code, phone, password)


def normalize_host(value: Any) -> str:
    """Validate a private or link-local phone IP address."""

    host = str(value or "").strip().rstrip(".")
    if not host:
        raise HelperError("missing_host", "Hãy nhập địa chỉ IP của điện thoại.")
    try:
        address = ip_address(host)
    except ValueError as error:
        raise HelperError(
            "invalid_host",
            "Hãy nhập địa chỉ IP LAN của điện thoại, không dùng hostname.",
        ) from error
    if not (address.is_private or address.is_link_local or address.is_loopback):
        raise HelperError(
            "non_local_host",
            "Địa chỉ điện thoại phải thuộc mạng LAN cục bộ.",
        )
    return str(address)


def normalize_port(value: Any, label: str = "Port") -> int:
    """Validate a TCP port."""

    try:
        port = int(value)
    except (TypeError, ValueError) as error:
        raise HelperError("invalid_port", f"{label} không hợp lệ.") from error
    if not 1 <= port <= 65535:
        raise HelperError("invalid_port", f"{label} không hợp lệ.")
    return port


def normalize_package(value: Any) -> str:
    """Validate an Android package name."""

    package_name = str(value or "").strip()
    if not _PACKAGE_PATTERN.fullmatch(package_name):
        raise HelperError("invalid_package", "Tên package Android không hợp lệ.")
    return package_name


def normalize_pairing_code(value: Any) -> str:
    """Validate the six-digit Android wireless pairing code."""

    code = str(value or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        raise HelperError("invalid_pairing_code", "Mã ghép đôi phải có 6 chữ số.")
    return code


def validate_records(raw_records: Any) -> list[LocalKeyRecord]:
    """Validate records returned by the Frida agent."""

    if not isinstance(raw_records, list):
        raise HelperError(
            "invalid_agent_result", "Dữ liệu từ app Android không hợp lệ."
        )

    records: dict[str, LocalKeyRecord] = {}
    for raw_record in raw_records:
        if not isinstance(raw_record, dict):
            continue
        device_id = _optional_text(raw_record.get("device_id"), 128)
        local_key = raw_record.get("local_key")
        if (
            not device_id
            or not _DEVICE_ID_PATTERN.fullmatch(device_id)
            or not isinstance(local_key, str)
            or len(local_key.encode("utf-8")) != 16
        ):
            continue
        host = _private_ip(raw_record.get("host"))
        protocol = _protocol_version(raw_record.get("protocol_version"))
        records[device_id] = LocalKeyRecord(
            device_id=device_id,
            local_key=local_key,
            name=_optional_text(raw_record.get("name"), 256),
            host=host,
            product_id=_optional_text(raw_record.get("product_id"), 256),
            protocol_version=protocol,
        )
    return [records[key] for key in sorted(records)]


def mask_local_key(value: str) -> str:
    """Mask a key for all user-visible output."""

    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:4]}…{value[-4:]}"


def _optional_text(value: Any, maximum: int) -> str | None:
    if value in (None, "") or isinstance(value, (dict, list, tuple, set)):
        return None
    text = str(value).strip()
    return text if 0 < len(text) <= maximum else None


def _private_ip(value: Any) -> str | None:
    text = _optional_text(value, 64)
    if not text:
        return None
    try:
        address = ip_address(text)
    except ValueError:
        return None
    return str(address) if address.is_private else None


def _protocol_version(value: Any) -> str | None:
    text = _optional_text(value, 16)
    if not text:
        return None
    try:
        version = f"{float(text):.1f}"
    except ValueError:
        return None
    return version if version in {"3.1", "3.2", "3.3", "3.4", "3.5"} else None
