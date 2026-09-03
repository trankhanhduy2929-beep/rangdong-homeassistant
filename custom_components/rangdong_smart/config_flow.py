"""Config flow for Rạng Đông Smart through Tuya QR authorization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests
import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.helpers import selector
from tuya_sharing import LoginControl

from .const import (
    CONF_ENDPOINT,
    CONF_TERMINAL_ID,
    CONF_TOKEN_INFO,
    CONF_USER_CODE,
    DOMAIN,
    QR_DESIGNATED_APP_CODES,
    QR_PAYLOAD_PREFIX,
    TUYA_CLIENT_ID,
    TUYA_SCHEMA,
)


def build_qr_payload(qr_token: str) -> str:
    """Build the QR payload accepted by the ThingClips scanner."""

    return f"{QR_PAYLOAD_PREFIX}{qr_token}"


class RangDongConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle QR-based authorization without asking for a password."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""

        self._login_control = LoginControl()
        self._user_code = ""
        self._qr_token = ""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the User Code shown by the mobile app."""

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
            step_id="user",
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

        if self.source == SOURCE_REAUTH:
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(),
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
        """Start QR reauthorization for an existing entry."""

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

    def _user_code_step_id(self) -> str:
        """Return the User Code step matching the current flow source."""

        return "reauth_user_code" if self.source == SOURCE_REAUTH else "user"

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
