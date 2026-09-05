"""Build-time downloads must never install unverified native inputs."""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path
from unittest.mock import patch

import pytest

BUILD_SCRIPT = Path(__file__).parents[1] / "build/download_apks.py"
SPEC = importlib.util.spec_from_file_location("download_apks", BUILD_SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_build_installs_both_verified_assets(tmp_path: Path) -> None:
    with (
        patch.object(
            MODULE.urllib.request,
            "urlopen",
            side_effect=lambda *args, **kwargs: io.BytesIO(b"fixture"),
        ),
        patch.object(MODULE, "verify_apk") as verify,
    ):
        MODULE.download_assets(tmp_path)
    assert [call.args[1] for call in verify.call_args_list] == ["base", "abi"]
    assert (tmp_path / "base.apk").read_bytes() == b"fixture"
    assert (tmp_path / "abi.apk").stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob("*.part"))


def test_build_rejects_oversized_download(tmp_path: Path) -> None:
    with (
        patch.object(
            MODULE.urllib.request, "urlopen", return_value=io.BytesIO(b"oversized")
        ),
        patch.object(MODULE, "MAX_APK_BYTES", 2),
        pytest.raises(ValueError),
    ):
        MODULE.download_assets(tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_build_rejects_wrong_hash(tmp_path: Path) -> None:
    from rangdong_helper.errors import HelperError

    with (
        patch.object(
            MODULE.urllib.request, "urlopen", return_value=io.BytesIO(b"untrusted")
        ),
        pytest.raises(HelperError),
    ):
        MODULE.download_assets(tmp_path)
    assert list(tmp_path.iterdir()) == []
