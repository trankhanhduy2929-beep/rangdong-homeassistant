"""Authenticated one-time bridge for importing keys from a user's device."""

from __future__ import annotations

from dataclasses import dataclass, field

from aiohttp import web
from homeassistant.components.http import HomeAssistantView, require_admin
from homeassistant.core import HomeAssistant
from homeassistant.helpers.http import KEY_HASS

from .const import (
    KEY_BRIDGE_API_PATH,
    KEY_BRIDGE_RUNTIME,
    KEY_BRIDGE_VIEW_REGISTERED,
)
from .key_sources import (
    LocalKeyRecord,
    RangDongKeyExportError,
    parse_local_key_export,
)

MAX_BRIDGE_BODY_BYTES = 512 * 1024


@dataclass(slots=True)
class KeyBridgeRuntime:
    """Hold imported records only for the lifetime of Home Assistant."""

    records: dict[str, LocalKeyRecord] = field(default_factory=dict)


def get_key_bridge_runtime(hass: HomeAssistant) -> KeyBridgeRuntime:
    """Return the in-memory bridge registry for this Home Assistant instance."""

    runtime = hass.data.get(KEY_BRIDGE_RUNTIME)
    if not isinstance(runtime, KeyBridgeRuntime):
        runtime = KeyBridgeRuntime()
        hass.data[KEY_BRIDGE_RUNTIME] = runtime
    return runtime


def get_key_bridge_records(hass: HomeAssistant) -> dict[str, LocalKeyRecord]:
    """Return a copy of records received from the local bridge."""

    return dict(get_key_bridge_runtime(hass).records)


def merge_key_bridge_records(
    hass: HomeAssistant,
    records: dict[str, LocalKeyRecord],
) -> dict[str, LocalKeyRecord]:
    """Merge validated records and return the resulting registry."""

    runtime = get_key_bridge_runtime(hass)
    runtime.records.update(records)
    return dict(runtime.records)


def remove_key_bridge_record(hass: HomeAssistant, device_id: str) -> None:
    """Remove one imported key after it has been consumed by setup."""

    get_key_bridge_runtime(hass).records.pop(device_id, None)


def clear_key_bridge_records(hass: HomeAssistant) -> None:
    """Remove all transient imported keys."""

    get_key_bridge_runtime(hass).records.clear()


def public_key_bridge_records(
    hass: HomeAssistant,
) -> list[dict[str, str | None]]:
    """Return metadata without exposing raw local keys."""

    return [
        {
            "device_id": record.device_id,
            "name": record.name,
            "host": record.host,
            "product_id": record.product_id,
            "protocol_version": record.protocol_version,
            "local_key": _mask_local_key(record.local_key),
        }
        for record in sorted(
            get_key_bridge_records(hass).values(),
            key=lambda item: item.device_id,
        )
    ]


def register_key_bridge(hass: HomeAssistant) -> None:
    """Register the authenticated import endpoint once."""

    get_key_bridge_runtime(hass)
    if hass.data.get(KEY_BRIDGE_VIEW_REGISTERED):
        return
    hass.http.register_view(RangDongKeyBridgeView())
    hass.data[KEY_BRIDGE_VIEW_REGISTERED] = True


class RangDongKeyBridgeView(HomeAssistantView):
    """Receive a one-time key export from a user-controlled helper."""

    url = KEY_BRIDGE_API_PATH
    name = "api:rangdong_smart:key_import"
    requires_auth = True
    cors_allowed = False

    @require_admin
    async def get(self, request: web.Request) -> web.Response:
        """List imported device metadata without returning raw keys."""

        records = public_key_bridge_records(request.app[KEY_HASS])
        return self.json({"success": True, "count": len(records), "devices": records})

    @require_admin
    async def post(self, request: web.Request) -> web.Response:
        """Parse and store a trusted export for the active setup flow."""

        hass = request.app[KEY_HASS]
        body = await request.content.read(MAX_BRIDGE_BODY_BYTES + 1)
        if len(body) > MAX_BRIDGE_BODY_BYTES:
            return self.json(
                {"success": False, "error": "payload_too_large"},
                status_code=413,
            )

        try:
            records = parse_local_key_export(body)
        except (RecursionError, UnicodeDecodeError, RangDongKeyExportError):
            return self.json(
                {"success": False, "error": "invalid_key_export"},
                status_code=400,
            )

        merged = merge_key_bridge_records(hass, records)
        return self.json(
            {
                "success": True,
                "count": len(records),
                "devices": [
                    item
                    for item in public_key_bridge_records(hass)
                    if item["device_id"] in records
                ],
                "available_count": len(merged),
            }
        )

    @require_admin
    async def delete(self, request: web.Request) -> web.Response:
        """Clear one record or the complete transient registry."""

        hass = request.app[KEY_HASS]
        device_id = str(request.query.get("device_id") or "").strip()
        if device_id:
            remove_key_bridge_record(hass, device_id)
        else:
            clear_key_bridge_records(hass)
        return self.json({"success": True, "devices": public_key_bridge_records(hass)})


def _mask_local_key(value: str) -> str:
    """Show only the shape of a local key to callers of the list endpoint."""

    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:4]}…{value[-4:]}"
