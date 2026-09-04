"""Boolean DP entities for local Rạng Đông devices."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RangDongLocalRuntimeData, is_local_entry
from .const import DOMAIN
from .coordinator import RangDongLocalCoordinator


async def async_setup_entry(
    hass,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one switch entity for every boolean local DP."""

    del hass
    if not is_local_entry(entry):
        return
    runtime = entry.runtime_data
    if not isinstance(runtime, RangDongLocalRuntimeData):
        return
    dps = runtime.coordinator.data or {}
    entities = [
        RangDongLocalDpsSwitch(runtime, dp_id, value)
        for dp_id, value in sorted(dps.items(), key=_dp_sort_key)
        if _is_boolean_value(value)
    ]
    async_add_entities(entities)


class RangDongLocalDpsSwitch(
    CoordinatorEntity[RangDongLocalCoordinator], SwitchEntity
):
    """Control one boolean Tuya data point over TCP 6668."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        runtime: RangDongLocalRuntimeData,
        dp_id: str,
        initial_value: Any,
    ) -> None:
        super().__init__(runtime.coordinator)
        self.runtime = runtime
        self.dp_id = str(dp_id)
        self._attr_unique_id = f"{DOMAIN}.{runtime.client.device_id}.dp_{self.dp_id}"
        self._attr_name = _dp_name(self.dp_id)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, runtime.client.device_id)},
            manufacturer="Rạng Đông / Tuya",
            name=runtime.name,
            model=runtime.product_id
            or f"Tuya LAN {runtime.client.protocol_version}",
        )
        self._state = bool(initial_value)

    @property
    def is_on(self) -> bool:
        """Return the latest boolean DP value."""

        value = (self.coordinator.data or {}).get(self.dp_id, self._state)
        self._state = bool(value)
        return self._state

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn this DP on."""

        del kwargs
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn this DP off."""

        del kwargs
        await self._async_set(False)

    async def _async_set(self, value: bool) -> None:
        await self.runtime.coordinator.async_set_dp(self.dp_id, value)
        self._state = value
        self.async_write_ha_state()


def _is_boolean_value(value: Any) -> bool:
    return isinstance(value, bool)


def _dp_name(dp_id: str) -> str:
    return "Power" if dp_id == "1" else f"Switch DP {dp_id}"


def _dp_sort_key(item: tuple[str, Any]) -> tuple[int, str]:
    dp_id = str(item[0])
    try:
        return int(dp_id), dp_id
    except ValueError:
        return 999999, dp_id
