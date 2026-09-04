"""Verify that an Ingress session belongs to a Home Assistant administrator."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from time import monotonic
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from .errors import HelperError

HOME_ASSISTANT_WEBSOCKET_URL = "ws://supervisor/core/websocket"
ADMIN_GROUP_ID = "system-admin"


@dataclass(frozen=True, slots=True)
class CachedAuthorization:
    """A short-lived administrator lookup."""

    is_admin: bool
    expires_at: float


class HomeAssistantUserAuthorizer:
    """Resolve Ingress user IDs through the authenticated Core WebSocket proxy."""

    def __init__(
        self,
        *,
        token: str | None = None,
        websocket_url: str = HOME_ASSISTANT_WEBSOCKET_URL,
        cache_seconds: float = 60,
    ) -> None:
        """Initialize the administrator verifier."""

        self._token = token if token is not None else os.getenv("SUPERVISOR_TOKEN", "")
        self._websocket_url = websocket_url
        self._cache_seconds = cache_seconds
        self._cache: dict[str, CachedAuthorization] = {}
        self._lock = asyncio.Lock()

    async def require_admin(self, user_id: str) -> None:
        """Raise unless the authenticated Ingress user is an administrator."""

        if not user_id:
            raise HelperError(
                "ingress_user_missing",
                "Không xác định được người dùng Home Assistant.",
                status=403,
            )
        cached = self._cache.get(user_id)
        if cached is not None and cached.expires_at > monotonic():
            if not cached.is_admin:
                raise _admin_required()
            return

        async with self._lock:
            cached = self._cache.get(user_id)
            if cached is not None and cached.expires_at > monotonic():
                if not cached.is_admin:
                    raise _admin_required()
                return
            users = await self._list_users()
            is_admin = any(
                str(user.get("id") or "") == user_id
                and (
                    bool(user.get("is_owner"))
                    or ADMIN_GROUP_ID in (user.get("group_ids") or [])
                )
                for user in users
                if isinstance(user, dict)
            )
            self._cache[user_id] = CachedAuthorization(
                is_admin,
                monotonic() + self._cache_seconds,
            )
        if not is_admin:
            raise _admin_required()

    async def _list_users(self) -> list[dict[str, Any]]:
        if not self._token:
            raise HelperError(
                "supervisor_token_missing",
                "Add-on không có quyền xác minh người dùng Home Assistant.",
                status=500,
            )
        timeout = ClientTimeout(total=15, connect=5)
        try:
            async with (
                ClientSession(timeout=timeout) as session,
                session.ws_connect(self._websocket_url) as websocket,
            ):
                required = await asyncio.wait_for(websocket.receive_json(), timeout=5)
                if required.get("type") != "auth_required":
                    raise RuntimeError("unexpected websocket authentication state")
                await websocket.send_json({"type": "auth", "access_token": self._token})
                authenticated = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=5,
                )
                if authenticated.get("type") != "auth_ok":
                    raise RuntimeError("websocket authentication failed")
                await websocket.send_json({"id": 1, "type": "config/auth/list"})
                response = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=5,
                )
        except HelperError:
            raise
        except Exception as error:
            raise HelperError(
                "admin_check_failed",
                "Không xác minh được quyền quản trị Home Assistant.",
                status=503,
            ) from error
        if (
            response.get("type") != "result"
            or response.get("id") != 1
            or not response.get("success")
            or not isinstance(response.get("result"), list)
        ):
            raise HelperError(
                "admin_check_failed",
                "Home Assistant không trả về danh sách người dùng hợp lệ.",
                status=503,
            )
        return response["result"]


def _admin_required() -> HelperError:
    return HelperError(
        "admin_required",
        "Chỉ quản trị viên Home Assistant được dùng Rạng Đông Key Helper.",
        status=403,
    )
