"""Local Tuya discovery and control helpers for Rạng Đông devices."""

from __future__ import annotations

import ipaddress
import socket
import threading
from dataclasses import dataclass
from typing import Any

TUYA_LOCAL_PORT = 6668
DISCOVERY_SECONDS = 8
PROTOCOL_FALLBACKS = ("3.5", "3.4", "3.3", "3.2", "3.1")


class RangDongLocalError(Exception):
    """Base error for local Rạng Đông communication."""


class RangDongLocalAuthError(RangDongLocalError):
    """Raised when the local key or protocol version is rejected."""


class RangDongLocalConnectionError(RangDongLocalError):
    """Raised when a device cannot be reached over the LAN."""


class RangDongLocalHostError(RangDongLocalError):
    """Raised when a host is not a private IPv4 address."""


@dataclass(frozen=True, slots=True)
class DiscoveredLocalDevice:
    """Safe metadata returned by Tuya UDP discovery."""

    device_id: str
    host: str
    product_id: str | None
    protocol_version: str | None
    name: str | None


@dataclass(frozen=True, slots=True)
class LocalProbeResult:
    """Validated protocol version and current data points."""

    protocol_version: str
    dps: dict[str, Any]


def normalize_local_host(value: str) -> str:
    """Validate and normalize a private IPv4 address."""

    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError as error:
        raise RangDongLocalHostError("Host must be a valid IPv4 address") from error
    if (
        address.version != 4
        or address.is_loopback
        or address.is_unspecified
        or address.is_multicast
        or not (address.is_private or address.is_link_local)
    ):
        raise RangDongLocalHostError("Host must be a private IPv4 address")
    return str(address)


def scan_lan_devices() -> dict[str, DiscoveredLocalDevice]:
    """Actively scan the LAN for Tuya-compatible devices."""

    try:
        import tinytuya
    except ImportError as error:
        raise RangDongLocalConnectionError("TinyTuya is not installed") from error

    try:
        discovered = tinytuya.deviceScan(
            verbose=False,
            maxretry=DISCOVERY_SECONDS,
            color=False,
            poll=False,
            forcescan=False,
        )
    except _tinytuya_error_types() as error:
        raise RangDongLocalConnectionError(
            "Unable to open the Tuya discovery sockets"
        ) from error
    if not isinstance(discovered, dict):
        return {}
    return normalize_discovery_results(discovered)


def normalize_discovery_results(
    discovered: dict[str, Any],
) -> dict[str, DiscoveredLocalDevice]:
    """Normalize TinyTuya scan results without retaining credentials."""

    devices: dict[str, DiscoveredLocalDevice] = {}
    for fallback_host, raw in discovered.items():
        if not isinstance(raw, dict):
            continue
        device_id = _first_text(raw, "gwId", "devId", "deviceId", "id")
        host = _first_text(raw, "ip") or str(fallback_host)
        if not device_id:
            continue
        try:
            host = normalize_local_host(host)
        except RangDongLocalHostError:
            continue
        version = _valid_protocol_version(
            _first_text(raw, "version", "ver", "protocolVersion")
        )
        devices[device_id] = DiscoveredLocalDevice(
            device_id=device_id,
            host=host,
            product_id=_first_text(raw, "productKey", "productId", "product_id"),
            protocol_version=version,
            name=_first_text(raw, "name"),
        )
    return dict(sorted(devices.items()))


def probe_local_device(
    host: str,
    device_id: str,
    local_key: str,
    protocol_version: str,
) -> LocalProbeResult:
    """Verify a local key and determine the working protocol version."""

    normalized_host = normalize_local_host(host)
    normalized_id = device_id.strip()
    normalized_key = local_key.strip()
    if not normalized_id:
        raise RangDongLocalAuthError("Device ID is required")
    if len(normalized_key) != 16:
        raise RangDongLocalAuthError("Local key must contain exactly 16 characters")

    try:
        with socket.create_connection((normalized_host, TUYA_LOCAL_PORT), timeout=3):
            pass
    except OSError as error:
        raise RangDongLocalConnectionError(
            f"Cannot reach {normalized_host}:{TUYA_LOCAL_PORT}"
        ) from error

    errors: list[str] = []
    connection_failures = 0
    for candidate in protocol_candidates(protocol_version):
        try:
            device = create_tinytuya_device(
                normalized_id,
                normalized_host,
                normalized_key,
                candidate,
            )
            response = device.status()
        except _tinytuya_error_types() as error:
            errors.append(f"{candidate}: {type(error).__name__}")
            connection_failures += 1
            continue
        dps = response_dps(response)
        if dps is not None:
            return LocalProbeResult(candidate, dps)
        if _response_is_connection_error(response):
            connection_failures += 1
        errors.append(f"{candidate}: {_response_error(response)}")

    detail = "; ".join(errors)[:500]
    if errors and connection_failures == len(errors):
        raise RangDongLocalConnectionError(
            "The device did not return a local status response"
            + (f" ({detail})" if detail else "")
        )
    raise RangDongLocalAuthError(
        "Device rejected the local key or protocol version"
        + (f" ({detail})" if detail else "")
    )


def protocol_candidates(protocol_version: str | None) -> tuple[str, ...]:
    """Return protocol versions to try in a deterministic order."""

    selected = _valid_protocol_version(protocol_version)
    if selected:
        return (selected,)
    return PROTOCOL_FALLBACKS


def create_tinytuya_device(
    device_id: str,
    host: str,
    local_key: str,
    protocol_version: str,
) -> Any:
    """Create a conservatively configured TinyTuya device object."""

    try:
        import tinytuya
    except ImportError as error:
        raise RangDongLocalConnectionError("TinyTuya is not installed") from error

    device_class = getattr(tinytuya, "OutletDevice", None) or tinytuya.Device
    device = device_class(
        device_id,
        host,
        local_key,
        version=float(protocol_version),
    )
    if hasattr(device, "set_version"):
        device.set_version(float(protocol_version))
    if hasattr(device, "set_socketPersistent"):
        device.set_socketPersistent(False)
    if hasattr(device, "set_socketRetryLimit"):
        device.set_socketRetryLimit(1)
    if hasattr(device, "set_socketTimeout"):
        device.set_socketTimeout(5)
    return device


def response_dps(response: Any) -> dict[str, Any] | None:
    """Extract normalized DPS values from a successful response."""

    if not isinstance(response, dict) or "Error" in response or "Err" in response:
        return None
    dps = response.get("dps")
    if not isinstance(dps, dict):
        return None
    return {str(dp_id): value for dp_id, value in dps.items()}


class RangDongLocalClient:
    """Serialize local status and command requests to one device."""

    def __init__(
        self,
        host: str,
        device_id: str,
        local_key: str,
        protocol_version: str,
    ) -> None:
        self.host = normalize_local_host(host)
        self.device_id = device_id.strip()
        normalized_key = local_key.strip()
        if not self.device_id:
            raise RangDongLocalAuthError("Device ID is required")
        if len(normalized_key) != 16:
            raise RangDongLocalAuthError(
                "Local key must contain exactly 16 characters"
            )
        self.protocol_version = protocol_candidates(protocol_version)[0]
        self._device = create_tinytuya_device(
            self.device_id,
            self.host,
            normalized_key,
            self.protocol_version,
        )
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        """Read all data points exposed by the device."""

        with self._lock:
            try:
                response = self._device.status()
            except Exception as error:
                raise RangDongLocalConnectionError(
                    f"Unable to read local device {self.device_id}"
                ) from error
        dps = response_dps(response)
        if dps is None:
            if _response_is_connection_error(response):
                raise RangDongLocalConnectionError(_response_error(response))
            raise RangDongLocalAuthError(_response_error(response))
        return dps

    def set_dp(self, dp_id: str | int, value: Any) -> dict[str, Any]:
        """Write one data point and return a fresh status snapshot."""

        with self._lock:
            try:
                response = self._device.set_value(str(dp_id), value)
                if response_dps(response) is None and _response_has_error(response):
                    raise RangDongLocalAuthError(_response_error(response))
                status = self._device.status()
            except RangDongLocalAuthError:
                raise
            except Exception as error:
                raise RangDongLocalConnectionError(
                    f"Unable to write local device {self.device_id}"
                ) from error
        dps = response_dps(status)
        if dps is None:
            if _response_is_connection_error(status):
                raise RangDongLocalConnectionError(_response_error(status))
            raise RangDongLocalAuthError(_response_error(status))
        return dps

    def close(self) -> None:
        """Close any TinyTuya socket retained by the client."""

        if hasattr(self._device, "set_socketPersistent"):
            self._device.set_socketPersistent(False)


def _first_text(raw: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def _valid_protocol_version(value: Any) -> str | None:
    if value in (None, "", "auto"):
        return None
    try:
        normalized = f"{float(value):.1f}"
    except (TypeError, ValueError):
        return None
    return normalized if normalized in PROTOCOL_FALLBACKS else None


def _response_has_error(response: Any) -> bool:
    return isinstance(response, dict) and ("Error" in response or "Err" in response)


def _response_error(response: Any) -> str:
    if not isinstance(response, dict):
        return "Invalid response from local device"
    return str(response.get("Error") or response.get("Err") or "Missing DPS response")


def _response_is_connection_error(response: Any) -> bool:
    if response is None:
        return True
    if not isinstance(response, dict):
        return False
    return str(response.get("Err", "")) in {"901", "902", "905"}


def _tinytuya_error_types() -> tuple[type[BaseException], ...]:
    """Return concrete exceptions used by TinyTuya and its transports."""

    try:
        import tinytuya
    except ImportError:
        return (OSError, ValueError, TypeError, RuntimeError)
    decode_error = getattr(tinytuya, "DecodeError", RuntimeError)
    return (OSError, ValueError, TypeError, RuntimeError, decode_error)
