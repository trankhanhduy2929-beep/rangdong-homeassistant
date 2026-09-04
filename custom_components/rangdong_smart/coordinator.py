"""Data coordinator for a local Rạng Đông device."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DEFAULT_SCAN_INTERVAL_SECONDS, DOMAIN
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

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.hass.async_add_executor_job(self.client.status)
        except RangDongLocalAuthError as error:
            raise ConfigEntryAuthFailed(str(error)) from error
        except RangDongLocalConnectionError as error:
            raise UpdateFailed(str(error)) from error

    async def async_set_dp(self, dp_id: str | int, value: Any) -> None:
        """Write one DP and publish the returned snapshot."""

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
