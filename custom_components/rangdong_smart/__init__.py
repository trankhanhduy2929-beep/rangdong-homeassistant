"""Rạng Đông Smart integration with local LAN and legacy QR support."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_NAME
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
    CONF_CONNECTION_TYPE,
    CONF_ENDPOINT,
    CONF_LOCAL_KEY,
    CONF_PRODUCT_ID,
    CONF_PROTOCOL_VERSION,
    CONF_TERMINAL_ID,
    CONF_TOKEN_INFO,
    CONF_USER_CODE,
    CONNECTION_LOCAL,
    DOMAIN,
    PLATFORMS,
    SERVICE_SEND_COMMAND,
    SIGNAL_DISCOVERY_NEW,
    SIGNAL_UPDATE_PREFIX,
    TUYA_CLIENT_ID,
)
from .coordinator import RangDongLocalCoordinator
from .key_bridge import register_key_bridge
from .local import RangDongLocalAuthError, RangDongLocalClient

LOGGER = logging.getLogger(__package__)
logging.getLogger("tuya_sharing").setLevel(logging.CRITICAL)
logging.getLogger("tinytuya").setLevel(logging.CRITICAL)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass(slots=True)
class RangDongCloudRuntimeData:
    """Runtime objects held for one authorized account."""

    manager: Manager
    listener: DeviceListener


@dataclass(slots=True)
class RangDongLocalRuntimeData:
    """Runtime objects held for one local device."""

    coordinator: RangDongLocalCoordinator
    client: RangDongLocalClient
    name: str
    product_id: str | None


type RangDongRuntimeData = RangDongCloudRuntimeData | RangDongLocalRuntimeData
type RangDongConfigEntry = ConfigEntry[RangDongRuntimeData]


def is_local_entry(entry: ConfigEntry) -> bool:
    """Return whether an entry uses direct LAN control."""

    return entry.data.get(CONF_CONNECTION_TYPE) == CONNECTION_LOCAL


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
    register_key_bridge(hass)
    if not hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        hass.services.async_register(
            DOMAIN,
            SERVICE_SEND_COMMAND,
            _async_send_command,
            schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICE_ID): cv.string,
                    vol.Optional("dp_id"): vol.Coerce(int),
                    vol.Optional("code"): cv.string,
                    vol.Required("value"): vol.Any(bool, int, float, str, dict, list),
                }
            ),
        )
    return True


async def _async_send_command(call: ServiceCall) -> None:
    """Send one generic DP command through the active connection type."""

    device_id = call.data[CONF_DEVICE_ID]
    for runtime in call.hass.data.get(DOMAIN, {}).values():
        if isinstance(runtime, RangDongLocalRuntimeData):
            if runtime.client.device_id != device_id:
                continue
            raw_dp_id = call.data.get("dp_id", call.data.get("code"))
            try:
                dp_id = int(raw_dp_id)
            except (TypeError, ValueError) as error:
                raise HomeAssistantError(
                    "Local control requires a numeric dp_id"
                ) from error
            await runtime.coordinator.async_set_dp(dp_id, call.data["value"])
            return

        if device_id in runtime.manager.device_map:
            code = call.data.get("code")
            if not code:
                raise HomeAssistantError("Legacy cloud control requires a DP code")
            command = {"code": code, "value": call.data["value"]}
            await call.hass.async_add_executor_job(
                runtime.manager.send_commands,
                device_id,
                [command],
            )
            return
    raise HomeAssistantError(f"Unknown Rạng Đông/Tuya device: {device_id}")


async def async_setup_entry(hass: HomeAssistant, entry: RangDongConfigEntry) -> bool:
    """Set up either a local device or a legacy QR account."""

    if is_local_entry(entry):
        return await _async_setup_local_entry(hass, entry)
    return await _async_setup_cloud_entry(hass, entry)


async def _async_setup_local_entry(
    hass: HomeAssistant, entry: RangDongConfigEntry
) -> bool:
    """Set up one directly controlled LAN device."""

    device_id = str(entry.data.get(CONF_DEVICE_ID, "unknown"))
    try:
        client = RangDongLocalClient(
            entry.data[CONF_HOST],
            entry.data[CONF_DEVICE_ID],
            entry.data[CONF_LOCAL_KEY],
            entry.data[CONF_PROTOCOL_VERSION],
        )
    except RangDongLocalAuthError as error:
        raise ConfigEntryAuthFailed(
            f"Invalid local credentials for Rạng Đông device {device_id}"
        ) from error
    except Exception as error:
        raise ConfigEntryNotReady(
            f"Unable to initialize local Rạng Đông device {device_id}"
        ) from error
    coordinator = RangDongLocalCoordinator(hass, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        client.close()
        raise
    except Exception as error:
        client.close()
        raise ConfigEntryNotReady(
            f"Unable to reach local Rạng Đông device {client.device_id}"
        ) from error

    runtime = RangDongLocalRuntimeData(
        coordinator=coordinator,
        client=client,
        name=entry.data.get(CONF_NAME) or entry.title,
        product_id=entry.data.get(CONF_PRODUCT_ID),
    )
    entry.runtime_data = runtime
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    async_get_device_registry(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, client.device_id)},
        manufacturer="Rạng Đông / Tuya",
        name=runtime.name,
        model=runtime.product_id or f"Tuya LAN {client.protocol_version}",
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_setup_cloud_entry(
    hass: HomeAssistant, entry: RangDongConfigEntry
) -> bool:
    """Set up a legacy QR-authorized cloud account."""

    token_listener = TokenListener(hass, entry)
    manager = await hass.async_add_executor_job(_create_manager, entry, token_listener)
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

    runtime = RangDongCloudRuntimeData(manager=manager, listener=listener)
    entry.runtime_data = runtime
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

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


async def async_unload_entry(hass: HomeAssistant, entry: RangDongConfigEntry) -> bool:
    """Unload entities and close the active transport."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    runtime = entry.runtime_data
    if isinstance(runtime, RangDongLocalRuntimeData):
        runtime.client.close()
    else:
        if runtime.manager.mq is not None:
            runtime.manager.mq.stop()
        try:
            runtime.manager.remove_device_listener(runtime.listener)
        except KeyError:
            pass
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: RangDongConfigEntry) -> None:
    """Revoke a legacy terminal authorization when its entry is removed."""

    if is_local_entry(entry):
        return

    token_info = entry.data.get(CONF_TOKEN_INFO)
    terminal_id = entry.data.get(CONF_TERMINAL_ID)
    endpoint = entry.data.get(CONF_ENDPOINT)
    user_code = entry.data.get(CONF_USER_CODE)
    if (
        not isinstance(token_info, Mapping)
        or not token_info.get("access_token")
        or not terminal_id
        or not endpoint
        or not user_code
    ):
        return

    manager = Manager(
        TUYA_CLIENT_ID,
        user_code,
        terminal_id,
        endpoint,
        dict(token_info),
    )
    try:
        await hass.async_add_executor_job(manager.unload)
    except Exception:
        LOGGER.debug("Unable to revoke the Tuya terminal authorization", exc_info=True)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Mark legacy entries as compatible with the dual-mode integration."""

    if entry.version < 4:
        hass.config_entries.async_update_entry(entry, version=4)
    return True
