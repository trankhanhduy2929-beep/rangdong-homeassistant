"""Config flow for local LAN setup and legacy QR authorization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests
import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    SOURCE_RECONFIGURE,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_NAME
from homeassistant.helpers import selector
from tuya_sharing import LoginControl

from .const import (
    CONF_CONNECTION_TYPE,
    CONF_DISCOVERED_DEVICE,
    CONF_ENDPOINT,
    CONF_LOCAL_KEY,
    CONF_PRODUCT_ID,
    CONF_PROTOCOL_VERSION,
    CONF_TERMINAL_ID,
    CONF_TOKEN_INFO,
    CONF_USER_CODE,
    CONNECTION_CLOUD_QR,
    CONNECTION_LOCAL,
    DEFAULT_PROTOCOL_VERSION,
    DISCOVERY_MANUAL,
    DOMAIN,
    PROTOCOL_VERSIONS,
    QR_DESIGNATED_APP_CODES,
    QR_PAYLOAD_PREFIX,
    TUYA_CLIENT_ID,
    TUYA_SCHEMA,
)
from .local import (
    DiscoveredLocalDevice,
    RangDongLocalAuthError,
    RangDongLocalConnectionError,
    RangDongLocalError,
    RangDongLocalHostError,
    normalize_local_host,
    probe_local_device,
    scan_lan_devices,
)


def build_qr_payload(qr_token: str) -> str:
    """Build the QR payload accepted by the ThingClips scanner."""

    return f"{QR_PAYLOAD_PREFIX}{qr_token}"


class RangDongConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up a local device or use the legacy QR flow."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the flow."""

        self._login_control = LoginControl()
        self._user_code = ""
        self._qr_token = ""
        self._connection_type = CONNECTION_LOCAL
        self._local_devices: dict[str, DiscoveredLocalDevice] = {}
        self._local_device_id = ""
        self._local_host = ""
        self._local_product_id = ""
        self._local_protocol_version = DEFAULT_PROTOCOL_VERSION
        self._local_scan_error = False

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose local LAN setup or the legacy QR flow."""

        if user_input is None:
            return self._show_connection_type_form()

        if CONF_CONNECTION_TYPE not in user_input and CONF_USER_CODE in user_input:
            return await self.async_step_cloud_qr(user_input)

        self._connection_type = user_input.get(CONF_CONNECTION_TYPE, CONNECTION_LOCAL)
        if self._connection_type == CONNECTION_LOCAL:
            return await self.async_step_local_scan()

        return await self.async_step_cloud_qr()

    async def async_step_local_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Scan the LAN and let the user choose a discovered device."""

        if user_input is None:
            self._local_scan_error = False
            try:
                self._local_devices = await self.hass.async_add_executor_job(
                    scan_lan_devices
                )
            except RangDongLocalError:
                self._local_devices = {}
                self._local_scan_error = True

            options = [
                {
                    "value": device_id,
                    "label": _discovered_device_label(device),
                }
                for device_id, device in self._local_devices.items()
            ]
            options.append({"value": DISCOVERY_MANUAL, "label": "Enter manually"})
            default = next(iter(self._local_devices), DISCOVERY_MANUAL)
            errors = {"base": "local_scan_failed"} if self._local_scan_error else {}
            return self.async_show_form(
                step_id="local_scan",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_DISCOVERED_DEVICE,
                            default=default,
                        ): selector.SelectSelector(
                            selector.SelectSelectorConfig(
                                options=options,
                                mode=selector.SelectSelectorMode.DROPDOWN,
                            )
                        )
                    }
                ),
                errors=errors,
            )

        selected_id = str(user_input.get(CONF_DISCOVERED_DEVICE, DISCOVERY_MANUAL))
        discovered = self._local_devices.get(selected_id)
        if discovered is None:
            self._local_device_id = ""
            self._local_host = ""
            self._local_product_id = ""
            self._local_protocol_version = DEFAULT_PROTOCOL_VERSION
        else:
            self._local_device_id = discovered.device_id
            self._local_host = discovered.host
            self._local_product_id = discovered.product_id or ""
            self._local_protocol_version = (
                discovered.protocol_version or DEFAULT_PROTOCOL_VERSION
            )
        return await self.async_step_local_device()

    async def async_step_local_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect a local key and verify direct LAN access."""

        errors: dict[str, str] = {}
        if user_input is not None:
            device_id = str(user_input.get(CONF_DEVICE_ID, "")).strip()
            host = str(user_input.get(CONF_HOST, "")).strip()
            local_key = str(user_input.get(CONF_LOCAL_KEY, "")).strip()
            protocol_version = str(
                user_input.get(CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION)
            )
            try:
                probe = await self.hass.async_add_executor_job(
                    probe_local_device,
                    host,
                    device_id,
                    local_key,
                    protocol_version,
                )
            except RangDongLocalAuthError:
                errors["base"] = "invalid_local_key"
            except RangDongLocalConnectionError:
                errors["base"] = "cannot_connect_local"
            except RangDongLocalHostError:
                errors["base"] = "invalid_local_host"
            except RangDongLocalError:
                errors["base"] = "local_setup_error"
            else:
                entry_data = {
                    CONF_CONNECTION_TYPE: CONNECTION_LOCAL,
                    CONF_DEVICE_ID: device_id,
                    CONF_HOST: normalize_local_host(host),
                    CONF_LOCAL_KEY: local_key,
                    CONF_PROTOCOL_VERSION: probe.protocol_version,
                    CONF_PRODUCT_ID: self._local_product_id or None,
                    CONF_NAME: str(user_input.get(CONF_NAME) or "").strip()
                    or f"Rạng Đông {device_id[-6:]}",
                }
                await self.async_set_unique_id(f"local:{device_id}")
                if self.source in {SOURCE_REAUTH, SOURCE_RECONFIGURE}:
                    self._abort_if_unique_id_mismatch()
                    entry = (
                        self._get_reauth_entry()
                        if self.source == SOURCE_REAUTH
                        else self._get_reconfigure_entry()
                    )
                    return self.async_update_reload_and_abort(
                        entry,
                        title=entry_data[CONF_NAME],
                        data=entry_data,
                    )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=entry_data[CONF_NAME],
                    data=entry_data,
                )

        return self._show_local_device_form(errors=errors, user_input=user_input)

    async def async_step_reauth_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-enter the local key for a local configuration."""

        return await self.async_step_local_device(user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update local addressing or credentials without deleting the entry."""

        entry_data = self._get_reconfigure_entry().data
        if entry_data.get(CONF_CONNECTION_TYPE) == CONNECTION_LOCAL:
            self._connection_type = CONNECTION_LOCAL
            self._local_device_id = str(entry_data.get(CONF_DEVICE_ID, ""))
            self._local_host = str(entry_data.get(CONF_HOST, ""))
            self._local_product_id = str(entry_data.get(CONF_PRODUCT_ID) or "")
            self._local_protocol_version = str(
                entry_data.get(CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION)
            )
            return await self.async_step_reconfigure_local(user_input)
        return await self.async_step_cloud_qr(user_input)

    async def async_step_reconfigure_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate updated local addressing and credentials."""

        return await self.async_step_local_device(user_input)

    async def async_step_cloud_qr(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the legacy QR User Code form."""

        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            success, response = await self._async_get_qr_code(
                user_input.get(CONF_USER_CODE, "")
            )
            if success:
                return await self.async_step_scan()
            errors["base"] = self._error_key(response)
            placeholders = self._error_placeholders(response)

        return self._show_user_code_form(
            step_id="cloud_qr",
            user_code=(user_input or {}).get(CONF_USER_CODE, ""),
            errors=errors,
            placeholders=placeholders,
        )

    async def async_step_scan(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the QR code and finish after the app approves it."""

        if user_input is None:
            if not self._user_code or not self._qr_token:
                return self._show_user_code_form(
                    step_id=self._user_code_step_id(),
                    user_code=self._user_code,
                )
            return self._show_scan_form()

        try:
            success, info = await self.hass.async_add_executor_job(
                self._login_control.login_result,
                self._qr_token,
                TUYA_CLIENT_ID,
                self._user_code,
            )
        except (requests.RequestException, ValueError, KeyError, TypeError):
            success, info = (
                False,
                {
                    "code": "NETWORK_ERROR",
                    "msg": "Unable to reach the Tuya authorization gateway",
                },
            )
        if not isinstance(info, Mapping):
            success, info = (
                False,
                {
                    "code": "INVALID_RESPONSE",
                    "msg": "Gateway returned an invalid login response",
                },
            )
        if not success:
            error_key = self._error_key(info)
            placeholders = self._error_placeholders(info)
            refreshed, refresh_response = await self._async_get_qr_code(self._user_code)
            if not refreshed:
                return self._show_user_code_form(
                    step_id=self._user_code_step_id(),
                    user_code=self._user_code,
                    errors={"base": self._error_key(refresh_response)},
                    placeholders=self._error_placeholders(refresh_response),
                )
            return self._show_scan_form(
                errors={"base": error_key},
                placeholders=placeholders,
            )

        try:
            entry_data = self._entry_data(info, self._user_code)
        except ValueError as error:
            return self._show_scan_form(
                errors={"base": "login_error"},
                placeholders={"code": "INVALID_RESPONSE", "msg": str(error)},
            )

        if self.source in {SOURCE_REAUTH, SOURCE_RECONFIGURE}:
            await self.async_set_unique_id(str(entry_data[CONF_TOKEN_INFO]["uid"]))
            self._abort_if_unique_id_mismatch()
            entry = (
                self._get_reauth_entry()
                if self.source == SOURCE_REAUTH
                else self._get_reconfigure_entry()
            )
            return self.async_update_reload_and_abort(
                entry,
                data=entry_data,
            )

        await self.async_set_unique_id(str(entry_data[CONF_TOKEN_INFO]["uid"]))
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=info.get("username") or "Rạng Đông Smart",
            data=entry_data,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthorization for the entry's connection type."""

        if entry_data.get(CONF_CONNECTION_TYPE) == CONNECTION_LOCAL:
            self._connection_type = CONNECTION_LOCAL
            self._local_device_id = str(entry_data.get(CONF_DEVICE_ID, ""))
            self._local_host = str(entry_data.get(CONF_HOST, ""))
            self._local_product_id = str(entry_data.get(CONF_PRODUCT_ID) or "")
            self._local_protocol_version = str(
                entry_data.get(CONF_PROTOCOL_VERSION, DEFAULT_PROTOCOL_VERSION)
            )
            return await self.async_step_reauth_local()

        if user_code := entry_data.get(CONF_USER_CODE):
            success, _ = await self._async_get_qr_code(str(user_code))
            if success:
                return await self.async_step_scan()
        return await self.async_step_reauth_user_code()

    async def async_step_reauth_user_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a replacement User Code during reauthorization."""

        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            success, response = await self._async_get_qr_code(
                user_input.get(CONF_USER_CODE, "")
            )
            if success:
                return await self.async_step_scan()
            errors["base"] = self._error_key(response)
            placeholders = self._error_placeholders(response)

        return self._show_user_code_form(
            step_id="reauth_user_code",
            user_code=(user_input or {}).get(CONF_USER_CODE, ""),
            errors=errors,
            placeholders=placeholders,
        )

    async def _async_get_qr_code(self, user_code: str) -> tuple[bool, dict[str, Any]]:
        """Request a temporary QR token from the Tuya gateway."""

        self._qr_token = ""
        normalized_code = user_code.strip()
        if not normalized_code:
            return False, {"code": "USERCODE_EMPTY", "msg": "User Code is required"}

        try:
            raw_response = await self.hass.async_add_executor_job(
                self._login_control.qr_code,
                TUYA_CLIENT_ID,
                TUYA_SCHEMA,
                normalized_code,
            )
        except (requests.RequestException, ValueError, KeyError, TypeError):
            return False, {
                "code": "NETWORK_ERROR",
                "msg": "Unable to reach the Tuya authorization gateway",
            }
        if not isinstance(raw_response, Mapping):
            return False, {
                "code": "INVALID_RESPONSE",
                "msg": "Gateway returned an invalid QR response",
            }
        response = dict(raw_response)

        if response.get("success"):
            result = response.get("result")
            if isinstance(result, Mapping):
                qr_token = result.get("qrcode") or result.get("qrCode")
                if isinstance(qr_token, str) and qr_token:
                    self._user_code = normalized_code
                    self._qr_token = qr_token
                    return True, response
            return False, {
                "code": "INVALID_RESPONSE",
                "msg": "Gateway returned no QR token",
            }
        return False, response

    def _show_user_code_form(
        self,
        *,
        step_id: str,
        user_code: str = "",
        errors: dict[str, str] | None = None,
        placeholders: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Render a User Code form for initial setup or reauthentication."""

        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USER_CODE,
                        default=user_code,
                    ): str,
                }
            ),
            errors=errors or {},
            description_placeholders=placeholders or {},
        )

    def _show_connection_type_form(self) -> ConfigFlowResult:
        """Render the initial connection selection."""

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONNECTION_TYPE,
                        default=CONNECTION_LOCAL,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                CONNECTION_LOCAL,
                                CONNECTION_CLOUD_QR,
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="connection_type",
                        )
                    )
                }
            ),
        )

    def _show_local_device_form(
        self,
        *,
        errors: dict[str, str] | None = None,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Render local device credentials and protocol settings."""

        values = user_input or {}
        device_id = str(values.get(CONF_DEVICE_ID, self._local_device_id))
        host = str(values.get(CONF_HOST, self._local_host))
        version = str(
            values.get(CONF_PROTOCOL_VERSION, self._local_protocol_version)
        )
        name = str(
            values.get(CONF_NAME)
            or (
                f"Rạng Đông {device_id[-6:]}"
                if device_id
                else "Rạng Đông Local"
            )
        )
        return self.async_show_form(
            step_id={
                SOURCE_REAUTH: "reauth_local",
                SOURCE_RECONFIGURE: "reconfigure_local",
            }.get(self.source, "local_device"),
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME, default=name): str,
                    vol.Required(CONF_HOST, default=host): str,
                    vol.Required(CONF_DEVICE_ID, default=device_id): str,
                    vol.Required(CONF_LOCAL_KEY): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Required(
                        CONF_PROTOCOL_VERSION,
                        default=version,
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(PROTOCOL_VERSIONS),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                            translation_key="protocol_version",
                        )
                    ),
                }
            ),
            errors=errors or {},
        )

    def _user_code_step_id(self) -> str:
        """Return the User Code step matching the current flow source."""

        return "reauth_user_code" if self.source == SOURCE_REAUTH else "cloud_qr"

    def _show_scan_form(
        self,
        errors: dict[str, str] | None = None,
        placeholders: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Render the QR step."""

        return self.async_show_form(
            step_id="scan",
            data_schema=vol.Schema(
                {
                    vol.Optional("qr"): selector.QrCodeSelector(
                        config=selector.QrCodeSelectorConfig(
                            data=build_qr_payload(self._qr_token),
                            scale=5,
                            error_correction_level=selector.QrErrorCorrectionLevel.QUARTILE,
                        )
                    )
                }
            ),
            errors=errors or {},
            description_placeholders=placeholders or {},
        )

    @staticmethod
    def _error_placeholders(response: Mapping[str, Any]) -> dict[str, str]:
        """Extract safe error fields for the translated form."""

        code = " ".join(str(response.get("code", "0")).split())[:64] or "0"
        message = (
            " ".join(str(response.get("msg", "Unknown error")).split())[:256]
            or "Unknown error"
        )
        return {
            "code": code,
            "msg": message,
        }

    @staticmethod
    def _error_key(response: Mapping[str, Any]) -> str:
        """Choose a useful message for a QR authorization failure."""

        code = str(response.get("code", "")).strip().upper()
        message = str(response.get("msg", "")).casefold()
        if code in QR_DESIGNATED_APP_CODES or "designated app" in message:
            return "designated_app_error"
        return "login_error"

    @staticmethod
    def _entry_data(info: Mapping[str, Any], user_code: str) -> dict[str, Any]:
        """Validate and normalize the SDK login result."""

        def pick(*keys: str) -> Any:
            for key in keys:
                value = info.get(key)
                if value not in (None, ""):
                    return value
            return None

        normalized = {
            "uid": pick("uid", "userId"),
            "terminal_id": pick("terminal_id", "terminalId"),
            "endpoint": pick("endpoint", "endPoint"),
            "access_token": pick("access_token", "accessToken"),
            "refresh_token": pick("refresh_token", "refreshToken"),
            "expire_time": pick("expire_time", "expireTime"),
            "t": pick("t"),
        }
        missing = [
            key
            for key in (
                "uid",
                "terminal_id",
                "endpoint",
                "access_token",
                "refresh_token",
                "expire_time",
                "t",
            )
            if not normalized[key]
        ]
        if missing:
            raise ValueError("Missing login field(s): " + ", ".join(missing))

        token_info = {
            "uid": normalized["uid"],
            "access_token": normalized["access_token"],
            "refresh_token": normalized["refresh_token"],
            "expire_time": normalized["expire_time"],
            "t": normalized["t"],
        }
        return {
            CONF_USER_CODE: user_code,
            CONF_TOKEN_INFO: token_info,
            CONF_TERMINAL_ID: str(normalized["terminal_id"]),
            CONF_ENDPOINT: str(normalized["endpoint"]),
        }


def _discovered_device_label(device: DiscoveredLocalDevice) -> str:
    """Build a compact, non-secret label for a scan result."""

    details = [device.host]
    if device.protocol_version:
        details.append(f"v{device.protocol_version}")
    if device.product_id:
        details.append(device.product_id)
    prefix = device.name or device.device_id
    return f"{prefix} ({', '.join(details)})"
