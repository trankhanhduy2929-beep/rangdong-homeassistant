"""Cloud worker, input and bridge tests using only synthetic credentials."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
from rangdong_helper.cloud import CloudClient, parse_cloud_login
from rangdong_helper.cloud_assets import verify_apk
from rangdong_helper.controller import HelperController
from rangdong_helper.errors import HelperError


def test_cloud_email_and_password_are_not_phone_normalized() -> None:
    result = parse_cloud_login(
        {
            "username": " test@example.invalid ",
            "password": " secret ",
            "country_code": "84",
        }
    )
    assert result == {
        "username": "test@example.invalid",
        "password": " secret ",
        "country_code": "84",
    }
    with pytest.raises(HelperError):
        parse_cloud_login({"username": "", "password": "secret"})


def test_untrusted_apk_rejected(tmp_path: Path) -> None:
    candidate = tmp_path / "bad.apk"
    candidate.write_bytes(b"untrusted native binary")
    with pytest.raises(HelperError, match="APK"):
        verify_apk(candidate, "base")


def test_bundled_assets_work_without_upload_and_survive_reset(tmp_path: Path) -> None:
    async def exercise() -> None:
        bundled = tmp_path / "bundled"
        bundled.mkdir()
        for name in ("base.apk", "abi.apk"):
            (bundled / name).write_bytes(b"fixture")
        private = tmp_path / "private"
        cloud = CloudClient(root=private, bundled_root=bundled)
        assert cloud.status()["bundled"] is True
        assert cloud.status()["base_uploaded"] is True
        private.mkdir()
        (private / "base.apk").write_bytes(b"partial override")
        assert cloud._asset_root() == bundled
        (private / "abi.apk").write_bytes(b"complete override")
        assert cloud._asset_root() == private
        (private / "prepared").mkdir()
        await cloud.clear_assets()
        assert not (private / "prepared").exists()
        assert cloud._asset_root() == bundled
        assert (bundled / "base.apk").read_bytes() == b"fixture"

    asyncio.run(exercise())


def test_upload_rejection_cleans_temporary_files(tmp_path: Path) -> None:
    class Stream:
        async def iter_chunked(self, size):
            yield b"invalid APK"

    async def exercise() -> None:
        client = CloudClient(root=tmp_path)
        with pytest.raises(HelperError):
            await client.upload("base", Stream())
        assert list(tmp_path.iterdir()) == []
        with (
            patch("rangdong_helper.cloud.MAX_APK_BYTES", 2),
            pytest.raises(HelperError) as error,
        ):
            await client.upload("abi", Stream())
        assert error.value.code == "apk_too_large"
        assert list(tmp_path.iterdir()) == []

    asyncio.run(exercise())


def test_cloud_bridge_receives_raw_key_but_status_is_masked() -> None:
    async def exercise() -> None:
        cloud = Mock()
        cloud.collect = AsyncMock(
            return_value=[
                {
                    "device_id": "test_device",
                    "local_key": "0123456789abcdef",
                    "name": "Đèn thử",
                }
            ]
        )
        cloud.status.return_value = {"supported": True}
        bridge = Mock()
        seen = []

        async def imported(records):
            seen.extend(record.as_bridge_payload() for record in records)
            return {"available_count": len(records)}

        bridge.import_records = AsyncMock(side_effect=imported)
        helper = HelperController(cloud=cloud, bridge=bridge)
        account = {
            "username": "test@example.invalid",
            "password": "secret",
            "country_code": "84",
        }
        result = await helper.cloud_scan(account)
        assert result["count"] == 1
        assert seen[0]["localKey"] == "0123456789abcdef"
        assert "0123456789abcdef" not in json.dumps(result)
        assert "secret" not in json.dumps(helper.status())
        assert not account

    asyncio.run(exercise())


def test_cloud_error_never_imports_and_clears_credentials() -> None:
    async def exercise() -> None:
        cloud = Mock()
        cloud.collect = AsyncMock(
            side_effect=HelperError("cloud_login_rejected", "Rejected")
        )
        bridge = Mock()
        bridge.import_records = AsyncMock()
        helper = HelperController(cloud=cloud, bridge=bridge)
        account = {
            "username": "test@example.invalid",
            "password": "secret",
            "country_code": "84",
        }
        with pytest.raises(HelperError):
            await helper.cloud_scan(account)
        bridge.import_records.assert_not_called()
        assert not account

    asyncio.run(exercise())


def test_worker_receives_credentials_only_on_stdin(tmp_path: Path) -> None:
    async def exercise() -> None:
        for name in ("base.apk", "abi.apk"):
            (tmp_path / name).write_bytes(b"fixture")
        (tmp_path / "prepared").mkdir()
        process = Mock()
        process.returncode = 0
        process.stdin.write = Mock()
        process.stdin.drain = AsyncMock()
        process.stdout.readuntil = AsyncMock(
            return_value=b'{"success":true,"devices":[]}\n'
        )
        process.wait = AsyncMock()
        launch = AsyncMock(return_value=process)
        credentials = {
            "username": "test@example.invalid",
            "password": "only-stdin",
            "country_code": "84",
        }
        with patch("rangdong_helper.cloud.asyncio.create_subprocess_exec", launch):
            result = await CloudClient(root=tmp_path).collect(credentials)
        assert result == []
        assert not credentials
        assert "only-stdin" not in str(launch.call_args)
        assert b"only-stdin" in process.stdin.write.call_args.args[0]
        assert launch.call_args.kwargs["stderr"] == asyncio.subprocess.DEVNULL
        assert set(launch.call_args.kwargs["env"]) == {"PATH", "HOME", "LANG"}

    asyncio.run(exercise())


def test_oversized_worker_output_is_reaped(tmp_path: Path) -> None:
    async def exercise() -> None:
        for name in ("base.apk", "abi.apk"):
            (tmp_path / name).write_bytes(b"fixture")
        (tmp_path / "prepared").mkdir()
        process = Mock()
        process.returncode = None
        process.stdin.drain = AsyncMock()
        process.stdout.readuntil = AsyncMock(
            side_effect=asyncio.LimitOverrunError("too large", 999999)
        )
        process.wait = AsyncMock()
        with (
            patch(
                "rangdong_helper.cloud.asyncio.create_subprocess_exec",
                AsyncMock(return_value=process),
            ),
            pytest.raises(HelperError),
        ):
            await CloudClient(root=tmp_path).collect(
                {"username": "test@example.invalid", "password": "secret"}
            )
        process.kill.assert_called_once()
        process.wait.assert_awaited()

    asyncio.run(exercise())
