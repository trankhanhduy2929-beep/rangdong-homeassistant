"""Chuẩn bị tài nguyên APK riêng tư; không in thông tin định danh ứng dụng."""

from __future__ import annotations

import argparse
import os
import re
import zipfile
from itertools import pairwise
from pathlib import Path

LIBRARIES = (
    "libc++_shared.so",
    "libmbedcrypto.so",
    "libmbedx509.so",
    "libmbedtls.so",
    "libthing_security_algorithm.so",
    "libthing_security.so",
)


def prepare(smali: Path, abi_apk: Path, output: Path) -> None:
    """Đọc APK do chủ tài khoản cung cấp, tạo thư mục mới có quyền 0700."""
    strings = re.findall(
        r'const-string(?:/jumbo)?\s+v\d+,\s+"([^"\n]*)"',
        smali.read_text(encoding="utf-8"),
    )
    pairs = {
        (app_id, secret)
        for app_id, secret in pairwise(strings)
        if re.fullmatch(r"[A-Za-z0-9]{20}", app_id)
        and re.fullmatch(r"[A-Za-z0-9]{32}", secret)
    }
    if len(pairs) != 1:
        raise ValueError("APK không khớp bố cục đã kiểm tra; dừng thay vì đoán khóa")
    app_id, app_secret = pairs.pop()
    libraries = {}
    with zipfile.ZipFile(abi_apk) as archive:
        for name in LIBRARIES:
            member = archive.getinfo(f"lib/armeabi-v7a/{name}")
            if member.file_size > 16 * 1024 * 1024:
                raise ValueError("Thư viện quá lớn")
            content = archive.read(member)
            if not content.startswith(b"\x7fELF\x01"):
                raise ValueError("Cần thư viện ELF 32-bit armeabi-v7a")
            libraries[name] = content
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    library_dir = output / "libs"
    library_dir.mkdir(mode=0o700)
    files = {
        output / "app-credentials": (app_id + "\n" + app_secret + "\n").encode(),
        **{library_dir / name: content for name, content in libraries.items()},
    }
    for path, content in files.items():
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write(content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smali", type=Path, required=True)
    parser.add_argument("--abi-apk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        prepare(args.smali, args.abi_apk, args.output)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        print("Chuẩn bị thất bại. Kiểm tra APK, smali và thư mục đích chưa tồn tại.")
        return 1
    print("Đã chuẩn bị tài nguyên riêng tư; không chia sẻ thư mục đầu ra.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
