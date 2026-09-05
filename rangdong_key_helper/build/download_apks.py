"""Fetch the immutable, hash-pinned APK pair while building the image."""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

from rangdong_helper.cloud_assets import MAX_APK_BYTES, verify_apk

BASE_URL = (
    "https://github.com/trankhanhduy2929-beep/rangdong-homeassistant/"
    "releases/download/native-resources-5.7.2/"
)


def download_assets(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    for kind, filename in (
        ("base", "com.rd.smart.apk"),
        ("abi", "config.armeabi_v7a.apk"),
    ):
        target = output / f"{kind}.apk"
        temporary = output / f"{kind}.part"
        try:
            with (
                urllib.request.urlopen(BASE_URL + filename, timeout=120) as response,
                temporary.open("wb") as destination,
            ):
                os.chmod(temporary, 0o600)
                total = 0
                while chunk := response.read(64 * 1024):
                    total += len(chunk)
                    if total > MAX_APK_BYTES:
                        raise ValueError("APK exceeds size limit")
                    destination.write(chunk)
            verify_apk(temporary, kind)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    download_assets(Path("/opt/rangdong-apk"))
