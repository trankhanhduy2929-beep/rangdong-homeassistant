"""Constants for the Rạng Đông Smart integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "rangdong_smart"
PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

CONF_CONNECTION_TYPE = "connection_type"
CONF_DISCOVERED_DEVICE = "discovered_device"
CONF_LOCAL_KEY = "local_key"
CONF_PRODUCT_ID = "product_id"
CONF_PROTOCOL_VERSION = "protocol_version"

CONNECTION_LOCAL = "local"
CONNECTION_CLOUD_QR = "cloud_qr"

DISCOVERY_MANUAL = "__manual__"
DEFAULT_PROTOCOL_VERSION = "auto"
DEFAULT_SCAN_INTERVAL_SECONDS = 10
PROTOCOL_VERSIONS = ("auto", "3.1", "3.2", "3.3", "3.4", "3.5")

CONF_ENDPOINT = "endpoint"
CONF_TERMINAL_ID = "terminal_id"
CONF_TOKEN_INFO = "token_info"
CONF_USER_CODE = "user_code"

TUYA_CLIENT_ID = "HA_3y9q4ak7g4ephrvke"
TUYA_SCHEMA = "haauthorize"
QR_PAYLOAD_PREFIX = "tuyaSmart--qrLogin?token="
QR_DESIGNATED_APP_CODES = frozenset({"E0020003"})

SIGNAL_DISCOVERY_NEW = f"{DOMAIN}_discovery_new"
SIGNAL_UPDATE_PREFIX = f"{DOMAIN}_update"
SERVICE_SEND_COMMAND = "send_command"

REDACTED = "<redacted>"
