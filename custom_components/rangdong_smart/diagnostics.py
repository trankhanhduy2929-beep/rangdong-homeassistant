"""Redacted diagnostics for the Rạng Đông Smart integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import RangDongLocalRuntimeData
from .const import DOMAIN, REDACTED

SENSITIVE_KEY_MARKERS = (
    "address",
    "bssid",
    "credential",
    "email",
    "image",
    "latitude",
    "local_key",
    "localkey",
    "location",
    "longitude",
    "mac",
    "mobile",
    "password",
    "phone",
    "secret",
    "ssid",
    "stream",
    "token",
    "uid",
    "unlock",
    "url",
    "video",
)


def _mask(value: Any) -> str:
    """Mask identifiers while retaining enough shape for troubleshooting."""

    if value in (None, ""):
        return REDACTED
    text = str(value)
    if len(text) <= 8:
        return REDACTED
    return f"{text[:4]}…{text[-4:]}"


def _safe_value(value: Any, key: str = "") -> Any:
    """Recursively remove credential-like fields."""

    lowered = key.lower()
    if any(marker in lowered for marker in SENSITIVE_KEY_MARKERS):
        return REDACTED
    if isinstance(value, dict):
        return {
            str(item_key): _safe_value(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_safe_value(item, key) for item in value]
    if isinstance(value, str) and len(value) > 128:
        return "<omitted>"
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return non-secret connection and device metadata."""

    del hass
    runtime = entry.runtime_data
    if isinstance(runtime, RangDongLocalRuntimeData):
        return {
            "domain": DOMAIN,
            "connection_type": "local",
            "device_id": _mask(runtime.client.device_id),
            "host": _mask(runtime.client.host),
            "protocol_version": runtime.client.protocol_version,
            "product_id": runtime.product_id,
            "connected": runtime.coordinator.last_update_success,
            "dps": _safe_value(runtime.coordinator.data or {}),
            "local_key": REDACTED,
        }

    manager = runtime.manager
    mqtt_client = manager.mq.client if manager.mq else None
    return {
        "domain": DOMAIN,
        "endpoint": manager.customer_api.endpoint,
        "terminal_id": _mask(manager.terminal_id),
        "mqtt_connected": mqtt_client.is_connected() if mqtt_client else False,
        "devices": [
            {
                "id": _mask(device.id),
                "name": device.name,
                "category": device.category,
                "product_id": device.product_id,
                "product_name": device.product_name,
                "online": device.online,
                "support_local": device.support_local,
                "status_codes": sorted(device.status),
                "function_codes": sorted(device.function),
                "status": _safe_value(device.status),
            }
            for device in manager.device_map.values()
        ],
    }
