"""Import only the exact owner-supplied APK pair verified by native research."""

from __future__ import annotations

import hashlib
import os
import shutil
import struct
import zipfile
from pathlib import Path

from .errors import HelperError

MAX_APK_BYTES = 160 * 1024 * 1024
APK_HASHES = {
    "base": "67c0fb602b55031117a09b4c0429be1270f60c8bf49e73dfec2b1aa6dbb43f8d",
    "abi": "7b72cab2b62ab5835a4e96ec38076fc08ab8899cca6ec1c43679d3a3ad4e6060",
}
LIBRARIES = (
    "libc++_shared.so",
    "libmbedcrypto.so",
    "libmbedx509.so",
    "libmbedtls.so",
    "libthing_security_algorithm.so",
    "libthing_security.so",
)


def verify_apk(path: Path, kind: str) -> None:
    """Never load an arbitrary uploaded native binary."""
    if (
        kind not in APK_HASHES
        or not path.is_file()
        or path.stat().st_size > MAX_APK_BYTES
    ):
        raise HelperError("invalid_apk", "File APK không hợp lệ hoặc quá lớn.")
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    if digest != APK_HASHES[kind]:
        raise HelperError(
            "unsupported_apk",
            "APK chưa được hỗ trợ. Cần đúng com.rd.smart 5.7.2 và split armeabi-v7a đã kiểm chứng; xem Hướng dẫn add-on.",
        )


def _dex_string(data: bytes, index: int) -> str:
    count, offset = struct.unpack_from("<II", data, 56)
    if not data.startswith(b"dex\n") or index >= count:
        raise ValueError("Unsupported dex")
    position = struct.unpack_from("<I", data, offset + 4 * index)[0]
    for _ in range(5):
        value = data[position]
        position += 1
        if not value & 128:
            break
    end = data.index(b"\0", position, position + 129)
    return data[position:end].decode("ascii")


def prepare_assets(base: Path, abi: Path, output: Path) -> None:
    """Extract fixed members only after verifying both entire APK hashes."""
    verify_apk(base, "base")
    verify_apk(abi, "abi")
    with zipfile.ZipFile(base) as archive:
        dex = archive.read("classes.dex")
    app_id = _dex_string(dex, 68478)
    app_secret = _dex_string(dex, 47794)
    if len(app_id) != 20 or len(app_secret) != 32:
        raise ValueError("Invalid APK credentials")
    output.mkdir(mode=0o700)
    library_dir = output / "libs"
    library_dir.mkdir(mode=0o700)
    with zipfile.ZipFile(abi) as archive:
        for name in LIBRARIES:
            content = archive.read(f"lib/armeabi-v7a/{name}")
            with (library_dir / name).open("xb") as target:
                os.chmod(target.name, 0o600)
                target.write(content)
    with (output / "app-credentials").open("xb") as target:
        os.chmod(target.name, 0o600)
        target.write(f"{app_id}\n{app_secret}\n".encode())
    shutil.copyfile(base, output / "base.apk")
    os.chmod(output / "base.apk", 0o600)
