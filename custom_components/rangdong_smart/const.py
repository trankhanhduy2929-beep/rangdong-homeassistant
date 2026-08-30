"""Constants for the Rạng Đông Smart diagnostic integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "rangdong_smart"
PLATFORMS = [Platform.SENSOR]

CONF_ENDPOINT = "endpoint"
CONF_TERMINAL_ID = "terminal_id"
CONF_TOKEN_INFO = "token_info"
CONF_USER_CODE = "user_code"

TUYA_CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
TUYA_SCHEMA = "haauthorize"

SIGNAL_DISCOVERY_NEW = f"{DOMAIN}_discovery_new"
SIGNAL_UPDATE_PREFIX = f"{DOMAIN}_update"
SERVICE_SEND_COMMAND = "send_command"

REDACTED = "<redacted>"
