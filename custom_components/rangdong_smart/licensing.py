"""Installation-bound licensing, isolated from running device control."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import time
import uuid
from typing import Any

from aiohttp import ClientError, ClientTimeout, web
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from homeassistant.components.http import HomeAssistantView, require_admin
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.http import KEY_HASS
from homeassistant.helpers.storage import Store

from . import license_config

RUNTIME_KEY = "rangdong_smart_license"
API_PATH = "/api/rangdong_smart/license"


def verify_lease(
    token: str,
    public_key: str,
    installation: str,
    component: str,
    client_id: str,
    now: float | None = None,
) -> dict[str, Any]:
    encoded, signature = token.split(".")
    if len(token) > 8192:
        raise ValueError("Invalid lease size")
    Ed25519PublicKey.from_public_bytes(
        base64.b64decode(public_key, validate=True)
    ).verify(
        base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)),
        encoded.encode(),
    )
    payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
    current = time.time() if now is None else now
    if (
        payload.get("v") != 1
        or payload.get("installation") != installation
        or payload.get("component") != component
        or payload.get("client_id") != client_id
        or not isinstance(payload.get("exp"), int)
        or not isinstance(payload.get("iat"), int)
        or payload["exp"] <= current
        or payload["iat"] > current + 300
        or payload["exp"] - payload["iat"] > 72 * 3600
    ):
        raise ValueError("Invalid lease binding or time")
    return payload


class LicenseManager:
    def __init__(self, hass: Any) -> None:
        self.hass = hass
        self._store = Store(hass, 1, RUNTIME_KEY, private=True, atomic_writes=True)
        self._state: dict[str, Any] | None = None
        self._lock = asyncio.Lock()

    async def _load(self) -> dict[str, Any]:
        if self._state is None:
            state = await self._store.async_load()
            if not isinstance(state, dict):
                private = Ed25519PrivateKey.generate().private_bytes(
                    serialization.Encoding.Raw,
                    serialization.PrivateFormat.Raw,
                    serialization.NoEncryption(),
                )
                state = {
                    "private": base64.b64encode(private).decode(),
                    "custom_id": str(uuid.uuid4()),
                    "key": "",
                    "leases": {},
                    "last_attempt": {},
                }
                await self._store.async_save(state)
            self._state = state
        return self._state

    async def check(
        self,
        component: str = "custom",
        client_id: str | None = None,
        key: str | None = None,
    ) -> dict[str, Any]:
        base = {
            "success": True,
            "buy_url": f"{license_config.SERVER_URL}/dashboard"
            if license_config.SERVER_URL
            else "",
            "enforced": license_config.ENFORCE,
        }
        if not license_config.ENFORCE:
            return {
                **base,
                "valid": True,
                "status": "compatibility",
                "message": "Chế độ tương thích: chưa bật license trên bản phân phối.",
            }
        if (
            not license_config.SERVER_URL.startswith("https://")
            or not license_config.VERIFY_PUBLIC_KEY
        ):
            return {**base, "valid": False, "status": "server_not_configured"}
        if component not in {"custom", "addon"}:
            raise ValueError("Invalid component")
        async with self._lock:
            state = await self._load()
            client_id = (
                state["custom_id"]
                if component == "custom"
                else str(uuid.UUID(str(client_id)))
            )
            candidate = key.strip().upper() if key is not None else state.get("key", "")
            if not re.fullmatch(r"RD-[A-F0-9]{48}", candidate):
                return {**base, "valid": False, "status": "license_required"}
            private = Ed25519PrivateKey.from_private_bytes(
                base64.b64decode(state["private"])
            )
            installation = base64.b64encode(
                private.public_key().public_bytes(
                    serialization.Encoding.Raw, serialization.PublicFormat.Raw
                )
            ).decode()
            cached = None
            slot = f"{component}:{client_id}"
            if key is None or candidate == state.get("key"):
                try:
                    cached = verify_lease(
                        state.get("leases", {}).get(slot, ""),
                        license_config.VERIFY_PUBLIC_KEY,
                        installation,
                        component,
                        client_id,
                    )
                except (InvalidSignature, ValueError, KeyError, TypeError):
                    cached = None
            now = int(time.time())
            last_attempt = state.setdefault("last_attempt", {}).get(slot, 0)
            if key is None and cached and now - cached["iat"] < 3600:
                return {
                    **base,
                    "valid": True,
                    "status": "active",
                    "expires_at": cached["exp"],
                }
            if now - last_attempt < 60:
                return {
                    **base,
                    "valid": bool(cached),
                    "status": "offline_grace" if cached else "retry_later",
                }
            state["last_attempt"][slot] = now
            payload = {
                "key": candidate,
                "installation": installation,
                "client_id": client_id,
                "component": component,
                "timestamp": now,
                "nonce": str(uuid.uuid4()),
            }
            message = "\n".join(
                str(value)
                for value in [
                    "rangdong-license-v1",
                    candidate,
                    installation,
                    client_id,
                    component,
                    now,
                    payload["nonce"],
                ]
            )
            payload["signature"] = base64.b64encode(
                private.sign(message.encode())
            ).decode()
            try:
                async with async_get_clientsession(self.hass).post(
                    f"{license_config.SERVER_URL}/api/licenses/activate",
                    json=payload,
                    timeout=ClientTimeout(total=15),
                    allow_redirects=False,
                ) as response:
                    raw = await response.content.read(16385)
                    if len(raw) > 16384:
                        raise ValueError("Oversized licensing response")
                    result = json.loads(raw)
                    if not isinstance(result, dict):
                        raise TypeError("Invalid licensing response")
                    if response.status in {400, 401, 403, 409, 404}:
                        if candidate == state.get("key"):
                            state["leases"] = {}
                        await self._store.async_save(state)
                        allowed = {
                            "license_invalid",
                            "license_bound",
                            "component_bound",
                            "invalid_proof",
                            "replayed_request",
                            "trial_already_used",
                        }
                        return {
                            **base,
                            "valid": False,
                            "status": result.get("error")
                            if result.get("error") in allowed
                            else "license_invalid",
                        }
                    if response.status != 200:
                        raise ValueError("Licensing service unavailable")
                    token = result["lease"]
                    lease = verify_lease(
                        token,
                        license_config.VERIFY_PUBLIC_KEY,
                        installation,
                        component,
                        client_id,
                    )
                    if candidate != state.get("key"):
                        state["leases"] = {}
                    state["key"] = candidate
                    state["leases"][slot] = token
                    await self._store.async_save(state)
                    return {
                        **base,
                        "valid": True,
                        "status": "active",
                        "expires_at": lease["exp"],
                    }
            except (
                ClientError,
                TimeoutError,
                ValueError,
                InvalidSignature,
                KeyError,
                TypeError,
            ):
                await self._store.async_save(state)
                return {
                    **base,
                    "valid": bool(cached),
                    "status": "offline_grace" if cached else "server_unavailable",
                }
            finally:
                payload.clear()


def manager(hass: Any) -> LicenseManager:
    if RUNTIME_KEY not in hass.data:
        hass.data[RUNTIME_KEY] = LicenseManager(hass)
    return hass.data[RUNTIME_KEY]


def register_license_view(hass: Any) -> None:
    if not hass.data.get(f"{RUNTIME_KEY}_view"):
        hass.http.register_view(LicenseView())
        hass.data[f"{RUNTIME_KEY}_view"] = True


class LicenseView(HomeAssistantView):
    url = API_PATH
    name = "api:rangdong_smart:license"
    requires_auth = True
    cors_allowed = False

    @require_admin
    async def get(self, request: web.Request) -> web.Response:
        try:
            result = await manager(request.app[KEY_HASS]).check(
                request.query.get("component", "custom"), request.query.get("client_id")
            )
            return self.json(result)
        except (ValueError, TypeError):
            return self.json(
                {"success": False, "error": "invalid_license_request"}, status_code=400
            )

    @require_admin
    async def post(self, request: web.Request) -> web.Response:
        payload = {}
        try:
            raw = await request.content.read(4097)
            if len(raw) > 4096:
                return self.json({"success": False}, status_code=413)
            payload = json.loads(raw)
            if not isinstance(payload, dict) or not isinstance(payload.get("key"), str):
                raise TypeError("Invalid payload")
            result = await manager(request.app[KEY_HASS]).check(
                payload.get("component", "custom"),
                payload.get("client_id"),
                payload["key"],
            )
            return self.json(result)
        except (ValueError, TypeError):
            return self.json(
                {"success": False, "error": "invalid_license_request"}, status_code=400
            )
        finally:
            if isinstance(payload, dict):
                payload.clear()
