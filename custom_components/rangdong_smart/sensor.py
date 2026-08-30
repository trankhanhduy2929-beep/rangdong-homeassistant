"""Generic device-summary sensors for Rạng Đông Smart."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from tuya_sharing import CustomerDevice, Manager

from .const import DOMAIN, SIGNAL_DISCOVERY_NEW, SIGNAL_UPDATE_PREFIX

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


def _redact_value(value: Any, key: str = "") -> Any:
    """Avoid exposing credential-like values from arbitrary Tuya DPs."""

    lowered_key = key.lower()
    if any(marker in lowered_key for marker in SENSITIVE_KEY_MARKERS):
        return "<redacted>"
    if isinstance(value, dict):
        return {
            str(item_key): _redact_value(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item, key) for item in value]
    if isinstance(value, str) and len(value) > 128:
        return "<omitted>"
    return value


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one generic status sensor per cloud device."""

    manager: Manager = entry.runtime_data.manager
    known_ids: set[str] = set()

    @callback
    def async_discover_devices(device_ids: Iterable[str]) -> None:
        entities: list[RangDongDeviceSummarySensor] = []
        for device_id in device_ids:
            if device_id in known_ids:
                continue
            device = manager.device_map.get(device_id)
            if device is None:
                continue
            known_ids.add(device_id)
            entities.append(RangDongDeviceSummarySensor(device, manager))
        if entities:
            async_add_entities(entities)

    async_discover_devices(manager.device_map)
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_DISCOVERY_NEW, async_discover_devices)
    )


class RangDongDeviceSummarySensor(SensorEntity):
    """Expose safe generic state/DP metadata for unsupported device types."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "Cloud status"

    def __init__(self, device: CustomerDevice, manager: Manager) -> None:
        """Initialize the summary sensor."""

        self.device = device
        self.manager = manager
        self._attr_unique_id = f"{DOMAIN}.{device.id}.summary"
        device.set_up = True

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry metadata."""

        return DeviceInfo(
            identifiers={(DOMAIN, self.device.id)},
            manufacturer="Rạng Đông / Tuya",
            name=self.device.name,
            model=self.device.product_name,
            model_id=self.device.product_id,
        )

    @property
    def native_value(self) -> str:
        """Return a stable human-readable state."""

        return "online" if self.device.online else "offline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose DP values while filtering credential-like fields."""

        return {
            "device_id": self.device.id,
            "category": self.device.category,
            "product_id": self.device.product_id,
            "support_local": self.device.support_local,
            "status_codes": sorted(self.device.status),
            "function_codes": sorted(self.device.function),
            "status": _redact_value(self.device.status),
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to SDK status updates."""

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_UPDATE_PREFIX}_{self.device.id}",
                self._async_handle_update,
            )
        )

    @callback
    def _async_handle_update(
        self,
        _updated_status_properties: list[str] | None = None,
        _dp_timestamps: dict[str, int] | None = None,
    ) -> None:
        """Refresh the state after an MQTT callback."""

        self.device = self.manager.device_map.get(self.device.id, self.device)
        self.async_write_ha_state()
