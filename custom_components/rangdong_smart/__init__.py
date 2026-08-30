"""Cloud-push diagnostic integration for Rạng Đông Smart/Tuya devices."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.dispatcher import dispatcher_send
from tuya_sharing import (
    CustomerDevice,
    Manager,
    SharingDeviceListener,
    SharingTokenListener,
)

from .const import (
    CONF_ENDPOINT,
    CONF_TERMINAL_ID,
    CONF_TOKEN_INFO,
    CONF_USER_CODE,
    DOMAIN,
    PLATFORMS,
    SERVICE_SEND_COMMAND,
    SIGNAL_DISCOVERY_NEW,
    SIGNAL_UPDATE_PREFIX,
    TUYA_CLIENT_ID,
)

LOGGER = logging.getLogger(__package__)
logging.getLogger("tuya_sharing").setLevel(logging.CRITICAL)


@dataclass(slots=True)
class RangDongRuntimeData:
    """Runtime objects held for one authorized account."""

    manager: Manager
    listener: DeviceListener


type RangDongConfigEntry = ConfigEntry[RangDongRuntimeData]


@dataclass(slots=True)
class TokenListener(SharingTokenListener):
    """Persist refreshed token metadata in the Home Assistant entry."""

    hass: HomeAssistant
    entry: RangDongConfigEntry

    def update_token(self, token_info: dict[str, Any]) -> None:
        """Update only the fields required by the SDK."""

        data = {
            **self.entry.data,
            CONF_TOKEN_INFO: {
                "t": token_info["t"],
                "uid": token_info["uid"],
                "expire_time": token_info["expire_time"],
                "access_token": token_info["access_token"],
                "refresh_token": token_info["refresh_token"],
            },
        }

        @callback
        def update_entry() -> None:
            self.hass.config_entries.async_update_entry(self.entry, data=data)

        self.hass.add_job(update_entry)


class DeviceListener(SharingDeviceListener):
    """Bridge SDK callbacks to Home Assistant dispatcher signals."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    def update_device(
        self,
        device: CustomerDevice,
        updated_status_properties: list[str] | None = None,
        dp_timestamps: dict[str, int] | None = None,
    ) -> None:
        dispatcher_send(
            self.hass,
            f"{SIGNAL_UPDATE_PREFIX}_{device.id}",
            updated_status_properties,
            dp_timestamps,
        )

    def add_device(self, device: CustomerDevice) -> None:
        dispatcher_send(self.hass, SIGNAL_DISCOVERY_NEW, [device.id])

    def remove_device(self, device_id: str) -> None:
        dispatcher_send(self.hass, f"{SIGNAL_UPDATE_PREFIX}_{device_id}", [], {})


def _create_manager(
    entry: RangDongConfigEntry, token_listener: TokenListener
) -> Manager:
    """Construct the SDK manager from the config entry."""

    return Manager(
        TUYA_CLIENT_ID,
        entry.data[CONF_USER_CODE],
        entry.data[CONF_TERMINAL_ID],
        entry.data[CONF_ENDPOINT],
        entry.data[CONF_TOKEN_INFO],
        token_listener,
    )


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register integration services."""

    del config
    hass.data.setdefault(DOMAIN, {})
    if not hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_COMMAND,
            _async_send_command,
            schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): cv.string,
                    vol.Required("code"): cv.string,
                    vol.Required("value"): vol.Any(
                        bool, int, float, str, dict, list
                    ),
                }
            ),
        )
    return True


async def _async_send_command(call: ServiceCall) -> None:
    """Send one generic Tuya DP command to a known device."""

    device_id = call.data[CONF_DEVICE_ID]
    command = {"code": call.data["code"], "value": call.data["value"]}
    for runtime in call.hass.data.get(DOMAIN, {}).values():
        if device_id in runtime.manager.device_map:
            await call.hass.async_add_executor_job(
                runtime.manager.send_commands,
                device_id,
                [command],
            )
            return
    raise HomeAssistantError(f"Unknown Rạng Đông/Tuya device: {device_id}")


async def async_setup_entry(
    hass: HomeAssistant, entry: RangDongConfigEntry
) -> bool:
    """Set up an authorized account and its device summaries."""

    token_listener = TokenListener(hass, entry)
    manager = await hass.async_add_executor_job(
        _create_manager, entry, token_listener
    )
    listener = DeviceListener(hass)
    manager.add_device_listener(listener)

    try:
        await hass.async_add_executor_job(manager.update_device_cache)
    except Exception as error:
        if "sign invalid" in str(error).lower():
            raise ConfigEntryAuthFailed(
                "Tuya authorization expired; please reauthenticate"
            ) from error
        raise ConfigEntryNotReady(
            "Unable to retrieve Rạng Đông Smart devices"
        ) from error

    entry.runtime_data = RangDongRuntimeData(manager=manager, listener=listener)
    hass.data[DOMAIN][entry.entry_id] = entry.runtime_data

    device_registry = async_get_device_registry(hass)
    for device in manager.device_map.values():
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, device.id)},
            manufacturer="Rạng Đông / Tuya",
            name=device.name,
            model=device.product_name,
            model_id=device.product_id,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    try:
        await hass.async_add_executor_job(manager.refresh_mq)
    except Exception:
        LOGGER.warning("MQTT state subscription could not be started", exc_info=True)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: RangDongConfigEntry
) -> bool:
    """Unload entities and stop the SDK MQTT worker."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    runtime = entry.runtime_data
    if runtime.manager.mq is not None:
        runtime.manager.mq.stop()
    try:
        runtime.manager.remove_device_listener(runtime.listener)
    except KeyError:
        pass
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def async_remove_entry(
    hass: HomeAssistant, entry: RangDongConfigEntry
) -> None:
    """Revoke the terminal authorization when the entry is removed."""

    manager = Manager(
        TUYA_CLIENT_ID,
        entry.data[CONF_USER_CODE],
        entry.data[CONF_TERMINAL_ID],
        entry.data[CONF_ENDPOINT],
        entry.data[CONF_TOKEN_INFO],
    )
    await hass.async_add_executor_job(manager.unload)
