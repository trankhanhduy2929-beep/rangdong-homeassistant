"""Upload one-time local-key records to Home Assistant Core."""

from __future__ import annotations

import os
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .constants import HOME_ASSISTANT_BRIDGE_URL, HOME_ASSISTANT_FLOW_URL
from .errors import HelperError
from .validation import LocalKeyRecord


class HomeAssistantBridge:
    """Call the administrator-protected integration bridge through Supervisor."""

    def __init__(
        self,
        *,
        token: str | None = None,
        url: str | None = None,
        flow_url: str | None = None,
    ) -> None:
        """Initialize the internal Home Assistant API client."""

        self._token = token if token is not None else os.getenv("SUPERVISOR_TOKEN", "")
        self._url = url or HOME_ASSISTANT_BRIDGE_URL
        self._flow_url = flow_url or HOME_ASSISTANT_FLOW_URL

    async def import_records(self, records: list[LocalKeyRecord]) -> dict[str, Any]:
        """Import records and return only the bridge's redacted response."""

        if not self._token:
            raise HelperError(
                "supervisor_token_missing",
                "Add-on không có quyền gọi Home Assistant API.",
                status=500,
            )
        payload = {"devices": [record.as_bridge_payload() for record in records]}
        try:
            response = await self._request("POST", self._url, json=payload)
        except HelperError as error:
            if error.code != "bridge_not_found":
                raise
            await self._activate_integration()
            response = await self._request("POST", self._url, json=payload)
        if not response.get("success"):
            raise HelperError(
                "bridge_import_failed",
                "Home Assistant từ chối dữ liệu local key.",
            )
        return response

    async def clear(self) -> dict[str, Any]:
        """Clear transient records from the integration bridge."""

        try:
            return await self._request("DELETE", self._url)
        except HelperError as error:
            if error.code != "bridge_not_found":
                raise
            return {"success": True, "devices": []}

    async def _activate_integration(self) -> None:
        """Load the config flow once so it can register the bridge view."""

        flow = await self._request(
            "POST",
            self._flow_url,
            not_found=(
                "integration_not_installed",
                "Không tìm thấy integration Rạng Đông Smart trong Home Assistant.",
            ),
            json={"handler": "rangdong_smart"},
        )
        flow_id = str(flow.get("flow_id") or "").strip()
        if not flow_id:
            raise HelperError(
                "integration_flow_failed",
                "Không khởi tạo được Rạng Đông Smart config flow.",
            )
        try:
            await self._request(
                "DELETE",
                f"{self._flow_url}/{flow_id}",
                not_found=(
                    "integration_flow_missing",
                    "Config flow tạm của Rạng Đông Smart không còn tồn tại.",
                ),
            )
        except HelperError as error:
            if error.code != "integration_flow_missing":
                raise

    async def _request(
        self,
        method: str,
        url: str,
        *,
        not_found: tuple[str, str] = (
            "bridge_not_found",
            "Chưa thấy bridge. Hãy cài/cập nhật integration rồi khởi động lại Home Assistant.",
        ),
        **kwargs: Any,
    ) -> dict[str, Any]:
        timeout = ClientTimeout(total=25, connect=10, sock_read=15)
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        try:
            async with (
                ClientSession(timeout=timeout) as session,
                session.request(
                    method,
                    url,
                    headers=headers,
                    **kwargs,
                ) as response,
            ):
                if response.status == 404:
                    raise HelperError(*not_found)
                if response.status in {401, 403}:
                    raise HelperError(
                        "bridge_unauthorized",
                        "Add-on không được Home Assistant cấp quyền quản trị bridge.",
                    )
                if response.status >= 400:
                    raise HelperError(
                        "bridge_request_failed",
                        f"Home Assistant trả về lỗi HTTP {response.status}.",
                    )
                data = await response.json(content_type=None)
        except HelperError:
            raise
        except Exception as error:
            raise HelperError(
                "bridge_unavailable",
                "Không kết nối được Home Assistant Core qua Supervisor.",
            ) from error
        if not isinstance(data, dict):
            raise HelperError(
                "bridge_invalid_response",
                "Phản hồi từ Home Assistant không hợp lệ.",
            )
        return data
