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
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from tuya_sharing import CustomerDevice, Manager

from . import RangDongLocalRuntimeData
from .const import DOMAIN, SIGNAL_DISCOVERY_NEW, SIGNAL_UPDATE_PREFIX
from .coordinator import RangDongLocalCoordinator

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
    """Create local or legacy cloud status sensors."""

    runtime = entry.runtime_data
    if isinstance(runtime, RangDongLocalRuntimeData):
        entities: list[SensorEntity] = [RangDongLocalStatusSensor(runtime)]
        entities.extend(
            RangDongLocalDpsSensor(runtime, dp_id)
            for dp_id, value in sorted(
                (runtime.coordinator.data or {}).items(), key=_dp_sort_key
            )
            if _is_sensor_value(value)
        )
        async_add_entities(entities)
        return

    manager: Manager = runtime.manager
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


class RangDongLocalStatusSensor(
    CoordinatorEntity[RangDongLocalCoordinator], SensorEntity
):
    """Expose the LAN connection and raw data-point snapshot."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_name = "LAN status"
    _attr_icon = "mdi:lan-connect"

    def __init__(self, runtime: RangDongLocalRuntimeData) -> None:
        super().__init__(runtime.coordinator)
        self.runtime = runtime
        self._attr_unique_id = f"{DOMAIN}.{runtime.client.device_id}.local_status"

    @property
    def native_value(self) -> str:
        return "connected" if self.coordinator.last_update_success else "disconnected"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.runtime.client.device_id)},
            manufacturer="Rạng Đông / Tuya",
            name=self.runtime.name,
            model=self.runtime.product_id
            or f"Tuya LAN {self.runtime.client.protocol_version}",
            model_id=self.runtime.product_id,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "device_id": self.runtime.client.device_id,
            "host": self.runtime.client.host,
            "protocol_version": self.runtime.client.protocol_version,
            "product_id": self.runtime.product_id,
            "dps": _redact_value(self.coordinator.data or {}),
        }


class RangDongLocalDpsSensor(
    CoordinatorEntity[RangDongLocalCoordinator], SensorEntity
):
    """Expose one scalar local data point as a sensor."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runtime: RangDongLocalRuntimeData, dp_id: str) -> None:
        super().__init__(runtime.coordinator)
        self.runtime = runtime
        self.dp_id = str(dp_id)
        self._attr_unique_id = (
            f"{DOMAIN}.{runtime.client.device_id}.sensor_dp_{self.dp_id}"
        )
        self._attr_name = f"DP {self.dp_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.client.device_id)},
            manufacturer="Rạng Đông / Tuya",
            name=runtime.name,
            model=runtime.product_id
            or f"Tuya LAN {runtime.client.protocol_version}",
            model_id=runtime.product_id,
        )

    @property
    def native_value(self) -> str | int | float | None:
        value = (self.coordinator.data or {}).get(self.dp_id)
        return value if _is_sensor_value(value) else None

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {"dp_id": self.dp_id}


def _is_sensor_value(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (str, int, float))


def _dp_sort_key(item: tuple[str, Any]) -> tuple[int, str]:
    dp_id = str(item[0])
    try:
        return int(dp_id), dp_id
    except ValueError:
        return 999999, dp_id


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
