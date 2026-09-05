"""Data coordinator for a local Rạng Đông device."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL_SECONDS, DOMAIN
from .licensing import manager as license_manager
from .local import (
    RangDongLocalAuthError,
    RangDongLocalClient,
    RangDongLocalConnectionError,
)


class RangDongLocalCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll and command one LAN device."""

    def __init__(self, hass, client: RangDongLocalClient) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=f"{DOMAIN}_{client.device_id}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.client = client
        self._cancel_license_expiry = None

    @callback
    def cancel_license_expiry(self) -> None:
        if self._cancel_license_expiry is not None:
            self._cancel_license_expiry()
            self._cancel_license_expiry = None

    async def _async_require_license(self) -> None:
        status = await license_manager(self.hass).check()
        self.cancel_license_expiry()
        if not status.get("valid"):
            raise HomeAssistantError(
                "Rạng Đông đang khóa: license hết hạn hoặc không xác minh được. "
                f"Gia hạn trên {status.get('buy_url', '')}; nếu có key mới, nhập trong Cấu hình tích hợp."
            )
        expires_at = status.get("expires_at")
        if expires_at is not None:
            remaining = expires_at - time.time()
            if remaining <= 0:
                raise HomeAssistantError("License Rạng Đông đã hết hạn. Hãy gia hạn trên website.")

            @callback
            def expired(_now) -> None:
                self._cancel_license_expiry = None
                self.async_set_update_error(UpdateFailed(
                    "License Rạng Đông cần xác minh/gia hạn trên website."
                ))

            self._cancel_license_expiry = async_call_later(self.hass, remaining, expired)

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            await self._async_require_license()
        except HomeAssistantError as error:
            raise UpdateFailed(str(error)) from error
        try:
            return await self.hass.async_add_executor_job(self.client.status)
        except RangDongLocalAuthError as error:
            raise ConfigEntryAuthFailed(str(error)) from error
        except RangDongLocalConnectionError as error:
            raise UpdateFailed(str(error)) from error

    async def async_set_dp(self, dp_id: str | int, value: Any) -> None:
        """Write one DP and publish the returned snapshot."""

        try:
            await self._async_require_license()
        except HomeAssistantError as error:
            self.async_set_update_error(UpdateFailed(str(error)))
            raise

        try:
            data = await self.hass.async_add_executor_job(
                self.client.set_dp,
                dp_id,
                value,
            )
        except RangDongLocalAuthError as error:
            raise ConfigEntryAuthFailed(str(error)) from error
        except RangDongLocalConnectionError as error:
            raise UpdateFailed(str(error)) from error
        self.async_set_updated_data(data)
