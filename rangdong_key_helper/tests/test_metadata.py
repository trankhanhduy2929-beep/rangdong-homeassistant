"""Validate app repository metadata and pinned versions."""

from __future__ import annotations

import json
import struct
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]
ADDON = ROOT / "rangdong_key_helper"


def test_repository_and_app_metadata() -> None:
    repository = yaml.safe_load((ROOT / "repository.yaml").read_text(encoding="utf-8"))
    config = yaml.safe_load((ADDON / "config.yaml").read_text(encoding="utf-8"))
    package = json.loads((ADDON / "agent/package.json").read_text(encoding="utf-8"))

    assert repository["name"] == "Rạng Đông Home Assistant"
    assert config["slug"] == "rangdong_key_helper"
    assert config["arch"] == ["aarch64", "amd64"]
    assert config["homeassistant"] == "2026.8.0"
    assert config["ingress"] is True
    assert "ingress_port" not in config
    assert "panel_admin" not in config
    assert "startup" not in config
    assert config["homeassistant_api"] is True
    assert config["image"].endswith("rangdong-key-helper")
    assert "watchdog" not in config
    assert package["version"] == config["version"]
    assert package["dependencies"]["frida-java-bridge"] == "7.0.13"
    assert not (ADDON / "build.yaml").exists()


def test_third_party_license_is_shipped_in_image() -> None:
    dockerfile = (ADDON / "Dockerfile").read_text(encoding="utf-8")
    notice = (ADDON / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    license_text = (ADDON / "LICENSE.frida.txt").read_text(encoding="utf-8")

    assert "COPY LICENSE THIRD_PARTY_NOTICES.md LICENSE.frida.txt" in dockerfile
    assert "HEALTHCHECK" in dockerfile
    assert "frida-java-bridge" in notice
    assert "GNU LIBRARY GENERAL PUBLIC LICENSE" in license_text
    assert "EXCEPTION NOTICE" in license_text


def test_app_store_images_are_valid_pngs() -> None:
    dimensions = {}
    for filename in ("icon.png", "logo.png"):
        data = (ADDON / filename).read_bytes()
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        dimensions[filename] = struct.unpack(">II", data[16:24])

    assert dimensions["icon.png"] == (128, 128)
    assert dimensions["logo.png"][0] > dimensions["logo.png"][1]


def test_compiled_agent_contains_expected_sdk_contract() -> None:
    agent = (ADDON / "rootfs/app/rangdong_helper/frida_agent.js").read_text(
        encoding="utf-8"
    )

    assert "com.thingclips.smart.home.sdk.ThingHomeSdk" in agent
    assert "loginWithPhonePassword" in agent
    assert "getLocalKey" in agent
    assert "Array.isArray" in agent
    assert "temporary-password" not in agent
