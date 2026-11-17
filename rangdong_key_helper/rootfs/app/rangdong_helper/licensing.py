"""License checks through the authenticated HA installation identity."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from pathlib import Path

from . import license_config
from .bridge import HomeAssistantBridge
from .errors import HelperError


class AddonLicense:
    def __init__(
        self,
        bridge: HomeAssistantBridge | None = None,
        identity_path: Path = Path("/data/license-client-id"),
    ) -> None:
        self._bridge = bridge or HomeAssistantBridge()
        self._identity_path = identity_path
        self._identity: str | None = None
        self._lock = asyncio.Lock()

    def _read_identity(self) -> str:
        self._identity_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            value = self._identity_path.read_text().strip()
        except FileNotFoundError:
            value = str(uuid.uuid4())
            descriptor = os.open(
                self._identity_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            with os.fdopen(descriptor, "w") as target:
                target.write(value)
        return str(uuid.UUID(value))

    async def status(self, key: str | None = None) -> dict:
        if not license_config.ENFORCE:
            return {
                "success": True,
                "valid": True,
                "status": "compatibility",
                "enforced": False,
                "buy_url": f"{license_config.SERVER_URL}/dashboard"
                if license_config.SERVER_URL
                else "",
            }
        async with self._lock:
            if self._identity is None:
                self._identity = await asyncio.to_thread(self._read_identity)
        result = await self._bridge.license_request(self._identity, key)
        expires_at = result.get("expires_at")
        if (
            result.get("enforced") is not True
            or result.get("status") != "active"
            or not isinstance(expires_at, (int, float))
            or expires_at <= time.time()
        ):
            return {**result, "valid": False}
        return result

    async def require_valid(self) -> None:
        result = await self.status()
        if license_config.ENFORCE and (
            result.get("enforced") is not True or result.get("valid") is not True
        ):
            raise HelperError(
                "license_required",
                "License chưa hợp lệ. Mở mục License để kích hoạt hoặc mua key.",
                status=403,
            )
