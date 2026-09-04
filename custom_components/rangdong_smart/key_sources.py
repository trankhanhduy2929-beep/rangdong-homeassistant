"""Local-key import helpers for Tuya-compatible Rạng Đông devices."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .local import RangDongLocalHostError, normalize_local_host, normalize_local_key

MAX_KEY_EXPORT_BYTES = 512 * 1024

TUYA_CLOUD_REGIONS = (
    "us",
    "us-e",
    "eu",
    "eu-w",
    "cn",
    "in",
    "sg",
)


class RangDongKeySourceError(Exception):
    """Base error for local-key import operations."""


class RangDongCloudKeyError(RangDongKeySourceError):
    """Raised when the Tuya Cloud request cannot provide local keys."""


class RangDongKeyExportError(RangDongKeySourceError):
    """Raised when an imported JSON export has no usable local keys."""


@dataclass(frozen=True, slots=True)
class LocalKeyRecord:
    """A local-key record with only metadata needed by the setup flow."""

    device_id: str
    local_key: str
    name: str | None = None
    host: str | None = None
    product_id: str | None = None
    protocol_version: str | None = None


def normalize_tuya_region(value: Any) -> str:
    """Validate a TinyTuya region identifier."""

    region = str(value or "").strip().lower()
    aliases = {"az": "us", "ue": "us-e", "we": "eu-w"}
    region = aliases.get(region, region)
    if region not in TUYA_CLOUD_REGIONS:
        raise RangDongCloudKeyError("Unsupported Tuya Cloud region")
    return region


def fetch_tuya_cloud_devices(
    api_region: str,
    access_id: str,
    access_secret: str,
    device_id: str | None = None,
) -> dict[str, LocalKeyRecord]:
    """Fetch local keys from a Tuya IoT Cloud project.

    The access secret is used only for the duration of this call.  Callers
    must not persist it in a config entry or diagnostics payload.
    """

    region = normalize_tuya_region(api_region)
    normalized_access_id = _required_text(access_id, "Access ID")
    normalized_access_secret = _required_text(access_secret, "Access Secret")
    requested_device_id = _optional_device_id(device_id)

    try:
        import tinytuya
    except ImportError as error:
        raise RangDongCloudKeyError("TinyTuya is not installed") from error

    try:
        cloud = tinytuya.Cloud(
            apiRegion=region,
            apiKey=normalized_access_id,
            apiSecret=normalized_access_secret,
            apiDeviceID=requested_device_id,
        )
        raw_devices = cloud.getdevices()
    except Exception as error:
        raise RangDongCloudKeyError(
            "Tuya Cloud did not return the device list"
        ) from error

    if _is_cloud_error(raw_devices):
        raise RangDongCloudKeyError("Tuya Cloud rejected the project credentials")
    if raw_devices == []:
        return {}

    try:
        records = parse_local_key_export(raw_devices)
    except RangDongKeyExportError as error:
        raise RangDongCloudKeyError(
            "Tuya Cloud returned no usable local keys"
        ) from error

    if requested_device_id:
        record = records.get(requested_device_id)
        if record is None:
            return {}
        return {requested_device_id: record}
    return records


def parse_local_key_export(
    export: str | bytes | Mapping[str, Any] | list[Any],
) -> dict[str, LocalKeyRecord]:
    """Parse common TinyTuya, LocalTuya and Tuya API JSON formats."""

    value = _decode_export(export)
    records: dict[str, LocalKeyRecord] = {}
    _walk_export(value, records)
    if not records:
        raise RangDongKeyExportError(
            "The export does not contain device IDs and 16-character local keys"
        )
    return dict(sorted(records.items()))


def records_from_existing_cloud_devices(devices: Any) -> dict[str, LocalKeyRecord]:
    """Extract keys from an already-authorized sharing SDK device map."""

    records: dict[str, LocalKeyRecord] = {}
    if isinstance(devices, Mapping):
        values = devices.values()
    elif isinstance(devices, (list, tuple, set)):
        values = devices
    else:
        return records
    for device in values:
        record = _record_from_object(device)
        if record is not None:
            records[record.device_id] = record
    return dict(sorted(records.items()))


def _decode_export(
    export: str | bytes | Mapping[str, Any] | list[Any],
) -> Any:
    if isinstance(export, bytes):
        if len(export) > MAX_KEY_EXPORT_BYTES:
            raise RangDongKeyExportError("The JSON export is too large")
        try:
            return json.loads(export.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RangDongKeyExportError("The JSON export is invalid") from error
    if isinstance(export, str):
        if len(export.encode("utf-8")) > MAX_KEY_EXPORT_BYTES:
            raise RangDongKeyExportError("The JSON export is too large")
        try:
            return json.loads(export)
        except json.JSONDecodeError as error:
            raise RangDongKeyExportError("The JSON export is invalid") from error
    if isinstance(export, (Mapping, list)):
        return export
    raise RangDongKeyExportError("The JSON export must be an object or list")


def _walk_export(
    value: Any,
    records: dict[str, LocalKeyRecord],
    fallback_device_id: str | None = None,
) -> None:
    if isinstance(value, Mapping):
        device_id = _first_text(value, _DEVICE_ID_FIELDS) or fallback_device_id
        local_key = _first_local_key(value, _LOCAL_KEY_FIELDS)
        if device_id and local_key:
            try:
                normalized_key = normalize_local_key(local_key)
            except ValueError:
                normalized_key = ""
            if normalized_key:
                record = LocalKeyRecord(
                    device_id=device_id,
                    local_key=normalized_key,
                    name=_first_text(value, ("name", "device_name", "deviceName")),
                    host=_private_host(value),
                    product_id=_first_text(
                        value,
                        (
                            "product_id",
                            "productId",
                            "product_key",
                            "productKey",
                        ),
                    ),
                    protocol_version=_protocol_version(
                        _first_value(
                            value,
                            (
                                "protocol_version",
                                "protocolVersion",
                                "version",
                                "ver",
                            ),
                        )
                    ),
                )
                records[device_id] = _merge_records(records.get(device_id), record)
        for key, child in value.items():
            child_fallback = None
            if (
                isinstance(child, Mapping)
                and _first_value(child, _LOCAL_KEY_FIELDS)
                and not _first_text(child, _DEVICE_ID_FIELDS)
            ):
                candidate = str(key).strip()
                if candidate and len(candidate) <= 128 and " " not in candidate:
                    child_fallback = candidate
            _walk_export(child, records, child_fallback)
        return
    if isinstance(value, list):
        for child in value:
            _walk_export(child, records)


def _record_from_object(device: Any) -> LocalKeyRecord | None:
    if isinstance(device, Mapping):
        values = device
        device_id = _first_text(values, _DEVICE_ID_FIELDS)
        local_key = _first_local_key(values, _LOCAL_KEY_FIELDS)
        name = _first_text(values, ("name", "device_name", "deviceName"))
        host = _private_host(values)
        product_id = _first_text(
            values, ("product_id", "productId", "product_key", "productKey")
        )
        protocol = _protocol_version(
            _first_value(values, ("protocol_version", "protocolVersion", "version"))
        )
    else:
        device_id = _first_attr(device, _DEVICE_ID_FIELDS)
        local_key = _first_local_key_attr(device, _LOCAL_KEY_FIELDS)
        name = _first_attr(device, ("name", "device_name", "deviceName"))
        host = _private_host_from_object(device)
        product_id = _first_attr(
            device, ("product_id", "productId", "product_key", "productKey")
        )
        protocol = _protocol_version(
            _first_attr(device, ("protocol_version", "protocolVersion", "version"))
        )
    if not device_id or not local_key:
        return None
    try:
        normalized_key = normalize_local_key(local_key)
    except ValueError:
        return None
    return LocalKeyRecord(
        device_id=device_id,
        local_key=normalized_key,
        name=name,
        host=host,
        product_id=product_id,
        protocol_version=protocol,
    )


def _merge_records(
    existing: LocalKeyRecord | None,
    incoming: LocalKeyRecord,
) -> LocalKeyRecord:
    if existing is None:
        return incoming
    return LocalKeyRecord(
        device_id=incoming.device_id,
        local_key=incoming.local_key,
        name=incoming.name or existing.name,
        host=incoming.host or existing.host,
        product_id=incoming.product_id or existing.product_id,
        protocol_version=incoming.protocol_version or existing.protocol_version,
    )


def _private_host(value: Mapping[str, Any]) -> str | None:
    host = _first_text(value, ("ip", "host", "address", "last_ip", "lastIp"))
    if not host:
        return None
    try:
        return normalize_local_host(host)
    except RangDongLocalHostError:
        return None


def _private_host_from_object(value: Any) -> str | None:
    host = _first_attr(value, ("ip", "host", "address", "last_ip", "lastIp"))
    if not host:
        return None
    try:
        return normalize_local_host(host)
    except RangDongLocalHostError:
        return None


def _protocol_version(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        version = f"{float(value):.1f}"
    except (TypeError, ValueError):
        version = str(value).strip()
    return version if version in {"3.1", "3.2", "3.3", "3.4", "3.5"} else None


def _first_text(value: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    item = _first_value(value, keys)
    if item in (None, "") or isinstance(item, (Mapping, list, tuple, set)):
        return None
    text = str(item).strip()
    if not text or len(text) > 256:
        return None
    return text


def _first_attr(value: Any, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        item = getattr(value, key, None)
        if item not in (None, "") and not isinstance(item, (Mapping, list, tuple, set)):
            text = str(item).strip()
            if text and len(text) <= 256:
                return text
    return None


def _first_local_key(value: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    item = _first_value(value, keys)
    if item in (None, "") or isinstance(item, (Mapping, list, tuple, set)):
        return None
    text = str(item)
    return text if len(text.encode("utf-8")) <= 256 else None


def _first_local_key_attr(value: Any, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        item = getattr(value, key, None)
        if item in (None, "") or isinstance(item, (Mapping, list, tuple, set)):
            continue
        text = str(item)
        if len(text.encode("utf-8")) <= 256:
            return text
    return None


def _first_value(value: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        item = value.get(key)
        if item not in (None, ""):
            return item
    return None


def _required_text(value: Any, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise RangDongCloudKeyError(f"{label} is required")
    if len(text) > 256:
        raise RangDongCloudKeyError(f"{label} is invalid")
    return text


def _optional_device_id(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) > 128 or " " in text:
        raise RangDongCloudKeyError("Device ID is invalid")
    return text


def _is_cloud_error(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    return "Error" in value or "Err" in value or value.get("success") is False


_DEVICE_ID_FIELDS = ("device_id", "deviceId", "devId", "gwId", "id")
_LOCAL_KEY_FIELDS = ("local_key", "localKey", "localkey", "key")
