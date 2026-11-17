"""License expiry blocks LAN commands without deleting device setup."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed
from rangdong_smart.config_flow import RangDongConfigFlow
from rangdong_smart.coordinator import RangDongLocalCoordinator
from rangdong_smart.local import DiscoveredLocalDevice, LocalProbeResult


def test_expiry_blocks_poll_and_command_then_renewal_restores_control():
    async def exercise():
        coordinator = object.__new__(RangDongLocalCoordinator)
        coordinator.hass = SimpleNamespace(
            async_add_executor_job=AsyncMock(return_value={"1": True})
        )
        coordinator.client = Mock()
        coordinator._cancel_license_expiry = None
        coordinator.async_set_update_error = Mock()
        coordinator.async_set_updated_data = Mock()
        with (
            patch("rangdong_smart.coordinator.license_manager") as manager,
            patch("rangdong_smart.coordinator.async_call_later") as timer,
        ):
            manager.return_value.check = AsyncMock(
                return_value={"valid": False, "buy_url": "https://example.invalid"}
            )
            with pytest.raises(HomeAssistantError):
                await coordinator.async_set_dp("1", True)
            with pytest.raises(UpdateFailed):
                await coordinator._async_update_data()
            coordinator.hass.async_add_executor_job.assert_not_called()
            manager.return_value.check.return_value = {
                "valid": True,
                "expires_at": time.time() - 1,
            }
            with pytest.raises(HomeAssistantError):
                await coordinator.async_set_dp("1", True)
            coordinator.hass.async_add_executor_job.assert_not_called()
            manager.return_value.check.return_value = {
                "valid": True,
                "expires_at": time.time() + 120,
            }
            await coordinator.async_set_dp("1", True)
            coordinator.hass.async_add_executor_job.assert_awaited_once_with(
                coordinator.client.set_dp, "1", True
            )
            coordinator.async_set_updated_data.assert_called_once_with({"1": True})
            timer.call_args.args[2](None)
            assert coordinator._cancel_license_expiry is None
            assert coordinator.async_set_update_error.call_count == 3

    asyncio.run(exercise())


def test_discovered_device_needs_only_key_and_retries_invalid_key():
    async def exercise():
        flow = RangDongConfigFlow()
        flow.hass = SimpleNamespace(data={}, http=SimpleNamespace(register_view=Mock()))
        flow.hass.async_add_executor_job = AsyncMock()
        flow.context = {"source": "user"}
        discovered = DiscoveredLocalDevice(
            "device-1", "192.168.1.20", "product-1", "3.5", "Đèn phòng khách"
        )
        flow.hass.async_add_executor_job.return_value = {"device-1": discovered}
        with patch("rangdong_smart.config_flow.license_manager") as manager:
            manager.return_value.check = AsyncMock(return_value={"valid": True})
            result = await flow.async_step_user()
        assert result["step_id"] == "local_scan"
        result = await flow.async_step_local_scan({"discovered_device": "device-1"})
        assert result["step_id"] == "local_discovered_key"
        assert [field.schema for field in result["data_schema"].schema] == ["local_key"]
        assert result["description_placeholders"]["name"] == "Đèn phòng khách"
        invalid = await flow.async_step_local_discovered_key({"local_key": "short"})
        assert invalid["errors"] == {"base": "invalid_local_key"}
        flow.hass.async_add_executor_job.return_value = LocalProbeResult(
            "3.5", {"1": True}
        )
        flow.async_set_unique_id = AsyncMock()
        flow._abort_if_unique_id_configured = Mock()
        result = await flow.async_step_local_discovered_key(
            {"local_key": "0123456789abcdef"}
        )
        assert result["type"] == "create_entry"
        assert result["data"]["device_id"] == "device-1"
        assert result["data"]["host"] == "192.168.1.20"
        assert result["data"]["name"] == "Đèn phòng khách"
        assert result["data"]["protocol_version"] == "3.5"

    asyncio.run(exercise())
