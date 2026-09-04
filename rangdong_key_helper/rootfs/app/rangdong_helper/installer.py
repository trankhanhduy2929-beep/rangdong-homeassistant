"""Download and verify a matching Frida server release."""

from __future__ import annotations

import asyncio
import hashlib
import lzma
import os
from dataclasses import dataclass
from pathlib import Path
from shutil import copyfileobj

from aiohttp import ClientSession, ClientTimeout

from .constants import FRIDA_ASSETS, FRIDA_VERSION, MAX_FRIDA_DOWNLOAD_BYTES
from .errors import HelperError


@dataclass(frozen=True, slots=True)
class FridaServerBinary:
    """A locally verified executable and its expected digest."""

    path: Path
    sha256: str


class FridaInstaller:
    """Cache only checksum-verified public Frida binaries."""

    def __init__(self, cache_directory: Path = Path("/data/frida")) -> None:
        """Initialize the persistent public binary cache."""

        self._cache_directory = cache_directory

    async def get_server(self, abi: str) -> FridaServerBinary:
        """Return the verified and decompressed server for an Android ABI."""

        asset = FRIDA_ASSETS.get(abi)
        if asset is None:
            raise HelperError(
                "unsupported_android_abi",
                f"CPU ABI {abi} chưa được Frida helper hỗ trợ.",
            )
        self._cache_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        compressed = self._cache_directory / asset.filename
        executable = self._cache_directory / asset.filename.removesuffix(".xz")

        if not await asyncio.to_thread(_matches_sha256, compressed, asset.sha256):
            await self._download(asset.url, compressed, asset.sha256)
        if not await asyncio.to_thread(
            _matches_sha256,
            executable,
            asset.executable_sha256,
        ):
            executable.unlink(missing_ok=True)
            await asyncio.to_thread(_decompress, compressed, executable)
        if not await asyncio.to_thread(
            _matches_sha256,
            executable,
            asset.executable_sha256,
        ):
            executable.unlink(missing_ok=True)
            raise HelperError(
                "frida_executable_checksum_failed",
                "Checksum Frida sau giải nén không khớp.",
            )
        executable.chmod(0o700)
        return FridaServerBinary(executable, asset.executable_sha256)

    async def _download(self, url: str, destination: Path, sha256: str) -> None:
        temporary = destination.with_suffix(f"{destination.suffix}.part")
        temporary.unlink(missing_ok=True)
        digest = hashlib.sha256()
        size = 0
        timeout = ClientTimeout(total=180, connect=20, sock_read=45)
        try:
            async with (
                ClientSession(timeout=timeout) as session,
                session.get(
                    url,
                    allow_redirects=True,
                    headers={"User-Agent": f"rangdong-key-helper/{FRIDA_VERSION}"},
                ) as response,
            ):
                if response.status != 200:
                    raise HelperError(
                        "frida_download_failed",
                        "Không tải được Frida server chính thức từ GitHub.",
                    )
                with temporary.open("wb") as output:
                    async for chunk in response.content.iter_chunked(128 * 1024):
                        size += len(chunk)
                        if size > MAX_FRIDA_DOWNLOAD_BYTES:
                            raise HelperError(
                                "frida_download_too_large",
                                "Tệp Frida tải về vượt giới hạn an toàn.",
                            )
                        digest.update(chunk)
                        output.write(chunk)
            if digest.hexdigest() != sha256:
                raise HelperError(
                    "frida_checksum_failed",
                    "Checksum Frida server không khớp; tệp đã bị loại bỏ.",
                )
            os.replace(temporary, destination)
        except HelperError:
            temporary.unlink(missing_ok=True)
            raise
        except Exception as error:
            temporary.unlink(missing_ok=True)
            raise HelperError(
                "frida_download_failed",
                "Không tải được Frida server chính thức từ GitHub.",
            ) from error


def _matches_sha256(path: Path, expected: str) -> bool:
    if not path.is_file():
        return False
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(128 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected


def _decompress(source: Path, destination: Path) -> None:
    temporary = destination.with_suffix(".part")
    temporary.unlink(missing_ok=True)
    try:
        with lzma.open(source, "rb") as compressed, temporary.open("wb") as output:
            copyfileobj(compressed, output, length=128 * 1024)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
