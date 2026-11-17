"""Offline lease verification and licensing isolation tests."""

import asyncio
import base64
import json
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from rangdong_smart.licensing import LicenseManager, verify_lease


def signed_fixture():
    private = Ed25519PrivateKey.generate()
    public = base64.b64encode(
        private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
    ).decode()
    now = int(time.time())
    payload = {
        "v": 1,
        "installation": "installation",
        "component": "custom",
        "client_id": "client",
        "iat": now,
        "exp": now + 3600,
    }
    encoded = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    )
    signature = (
        base64.urlsafe_b64encode(private.sign(encoded.encode())).decode().rstrip("=")
    )
    return f"{encoded}.{signature}", public, now


def test_signed_lease_rejects_wrong_installation_component_and_expiry():
    token, public, now = signed_fixture()
    assert (
        verify_lease(token, public, "installation", "custom", "client", now)["exp"]
        == now + 3600
    )
    for installation, component, client, current in [
        ("other", "custom", "client", now),
        ("installation", "addon", "client", now),
        ("installation", "custom", "other", now),
        ("installation", "custom", "client", now + 3601),
    ]:
        with pytest.raises(ValueError):
            verify_lease(token, public, installation, component, client, current)


def test_compatibility_mode_never_contacts_network_or_changes_devices():
    async def exercise():
        with (
            patch("rangdong_smart.licensing.Store") as store,
            patch("rangdong_smart.licensing.license_config.ENFORCE", False),
            patch("rangdong_smart.licensing.async_get_clientsession") as session,
        ):
            manager = LicenseManager(Mock())
            result = await manager.check()
            assert result["valid"] is True
            assert result["status"] == "compatibility"
            store.return_value.async_load.assert_not_called()
            session.assert_not_called()

    asyncio.run(exercise())


def test_enforced_unconfigured_server_fails_closed_without_network():
    async def exercise():
        with (
            patch("rangdong_smart.licensing.Store"),
            patch("rangdong_smart.licensing.license_config.ENFORCE", True),
            patch("rangdong_smart.licensing.license_config.SERVER_URL", ""),
            patch("rangdong_smart.licensing.async_get_clientsession") as session,
        ):
            result = await LicenseManager(Mock()).check()
            assert result["valid"] is False
            session.assert_not_called()

    asyncio.run(exercise())


@pytest.mark.parametrize("component", ["custom", "addon"])
def test_network_failure_uses_signed_grace_but_revocation_clears_lease(component):
    async def exercise():
        private = Ed25519PrivateKey.generate()
        signer = Ed25519PrivateKey.generate()
        public = base64.b64encode(
            signer.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        ).decode()
        installation = base64.b64encode(
            private.public_key().public_bytes(
                serialization.Encoding.Raw, serialization.PublicFormat.Raw
            )
        ).decode()
        now = int(time.time())
        payload = {
            "v": 1,
            "installation": installation,
            "component": component,
            "client_id": "11111111-1111-4111-8111-111111111111",
            "iat": now - 7200,
            "exp": now + 3600,
        }
        encoded = (
            base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        )
        signature = (
            base64.urlsafe_b64encode(signer.sign(encoded.encode())).decode().rstrip("=")
        )
        state = {
            "private": base64.b64encode(
                private.private_bytes(
                    serialization.Encoding.Raw,
                    serialization.PrivateFormat.Raw,
                    serialization.NoEncryption(),
                )
            ).decode(),
            "custom_id": "11111111-1111-4111-8111-111111111111",
            "key": "RD-" + "A" * 48,
            "leases": {
                f"{component}:11111111-1111-4111-8111-111111111111": encoded
                + "."
                + signature
            },
            "last_attempt": {},
        }
        with (
            patch("rangdong_smart.licensing.Store") as store,
            patch("rangdong_smart.licensing.license_config.ENFORCE", True),
            patch(
                "rangdong_smart.licensing.license_config.SERVER_URL",
                "https://license.example.invalid",
            ),
            patch("rangdong_smart.licensing.license_config.VERIFY_PUBLIC_KEY", public),
            patch("rangdong_smart.licensing.async_get_clientsession") as session,
        ):
            store.return_value.async_load = AsyncMock(return_value=state)
            store.return_value.async_save = AsyncMock()
            session.return_value.post.side_effect = TimeoutError()
            manager = LicenseManager(Mock())
            result = await manager.check(component, state["custom_id"])
            assert result["valid"] is False
            assert result["status"] == "server_unavailable"
            automatic = await manager.check(component, state["custom_id"])
            assert automatic["status"] == "retry_later"
            session.return_value.post.reset_mock()
            explicit = await manager.check(
                component, state["custom_id"], "RD-" + "B" * 48
            )
            assert explicit["status"] == "server_unavailable"
            session.return_value.post.assert_called_once()
            repeated = await manager.check(
                component, state["custom_id"], "RD-" + "C" * 48
            )
            assert repeated["status"] == "retry_later"
            assert 1 <= repeated["retry_after"] <= 5
            session.return_value.post.assert_called_once()
            state["last_attempt"] = {}
            session.return_value.post.side_effect = None
            response = Mock()
            response.status = 403
            response.content.read = AsyncMock(
                return_value=b'{"error":"license_invalid"}'
            )
            context = AsyncMock()
            context.__aenter__.return_value = response
            session.return_value.post.return_value = context
            result = await manager.check(component, state["custom_id"])
            assert result["valid"] is False
            assert state["leases"] == {}
            assert "key" not in result

    asyncio.run(exercise())
