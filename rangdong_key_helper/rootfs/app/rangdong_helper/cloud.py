"""One-shot native cloud worker; no persisted account, session or device keys."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import platform
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from .cloud_assets import MAX_APK_BYTES, prepare_assets, verify_apk
from .errors import HelperError

MAX_WORKER_BYTES = 512 * 1024


def parse_cloud_login(payload: dict[str, Any]) -> dict[str, str]:
    """Validate input without normalizing or logging the password."""
    account = payload.get("username")
    country = payload.get("country_code", "84")
    password = payload.get("password")
    if not isinstance(account, str) or not 3 <= len(account.strip()) <= 254:
        raise HelperError("invalid_account", "Nhập email hoặc số điện thoại Rạng Đông.")
    if (
        not isinstance(country, str)
        or not country.isascii()
        or not country.isdigit()
        or not 1 <= len(country) <= 4
    ):
        raise HelperError("invalid_country_code", "Mã quốc gia không hợp lệ.")
    if not isinstance(password, str) or not 4 <= len(password) <= 128:
        raise HelperError("invalid_password", "Mật khẩu không hợp lệ.")
    return {"username": account.strip(), "country_code": country, "password": password}


class CloudClient:
    """Serialize via the controller and isolate every login in a fresh process."""

    def __init__(
        self,
        root: Path = Path("/data/cloud"),
        classpath: str = "/app/native/classes:/app/native/lib/*",
        bundled_root: Path = Path("/opt/rangdong-apk"),
    ) -> None:
        self.root = root
        self.classpath = classpath
        self.bundled_root = bundled_root
        self.process: asyncio.subprocess.Process | None = None
        self._last_attempt = 0.0

    def status(self) -> dict[str, Any]:
        assets = self._asset_root()
        return {
            "supported": platform.machine().lower()
            in {"x86_64", "amd64", "aarch64", "arm64"},
            "base_uploaded": (assets / "base.apk").is_file(),
            "abi_uploaded": (assets / "abi.apk").is_file(),
            "bundled": assets == self.bundled_root,
            "apk_version": "5.7.2",
        }

    def _asset_root(self) -> Path:
        if all((self.root / name).is_file() for name in ("base.apk", "abi.apk")):
            return self.root
        if all(
            (self.bundled_root / name).is_file() for name in ("base.apk", "abi.apk")
        ):
            return self.bundled_root
        return self.root

    def _mkdir(self) -> None:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)

    async def upload(self, kind: str, stream: Any) -> None:
        if kind not in {"base", "abi"}:
            raise HelperError("invalid_apk_kind", "Loại APK không hợp lệ.")
        self._mkdir()
        descriptor, filename = tempfile.mkstemp(prefix="upload-", dir=self.root)
        temporary = Path(filename)
        try:
            with os.fdopen(descriptor, "wb") as target:
                size = 0
                async for chunk in stream.iter_chunked(64 * 1024):
                    size += len(chunk)
                    if size > MAX_APK_BYTES:
                        raise HelperError(
                            "apk_too_large", "APK vượt giới hạn 160 MiB.", status=413
                        )
                    target.write(chunk)
            await asyncio.to_thread(verify_apk, temporary, kind)
            temporary.replace(self.root / f"{kind}.apk")
            shutil.rmtree(self.root / "prepared", ignore_errors=True)
        finally:
            temporary.unlink(missing_ok=True)

    async def clear_assets(self) -> None:
        for name in ("base.apk", "abi.apk"):
            (self.root / name).unlink(missing_ok=True)
        await asyncio.to_thread(shutil.rmtree, self.root / "prepared", True)

    async def collect(self, credentials: dict[str, str]) -> list[dict[str, Any]]:
        if not self.status()["supported"]:
            raise HelperError(
                "cloud_arch_unsupported", "Chế độ cloud cần máy amd64 hoặc aarch64."
            )
        if not all(self.status()[field] for field in ("base_uploaded", "abi_uploaded")):
            raise HelperError(
                "cloud_apk_missing",
                "Hãy tải lên cả base APK và split armeabi-v7a trước.",
            )
        if self._last_attempt and time.monotonic() - self._last_attempt < 60:
            raise HelperError(
                "cloud_cooldown",
                "Chờ 60 giây trước khi thử đăng nhập tiếp.",
                status=429,
            )
        self._last_attempt = time.monotonic()
        self._mkdir()
        prepared = self.root / "prepared"
        assets = self._asset_root()
        if not prepared.exists():
            temporary = Path(tempfile.mkdtemp(prefix="prepare-", dir=self.root))
            task = asyncio.create_task(
                asyncio.to_thread(
                    prepare_assets,
                    assets / "base.apk",
                    assets / "abi.apk",
                    temporary / "assets",
                )
            )
            try:
                await asyncio.shield(task)
                (temporary / "assets").replace(prepared)
            except (OSError, ValueError, zipfile.BadZipFile, KeyError, HelperError):
                raise HelperError(
                    "cloud_prepare_failed",
                    "Không chuẩn bị được APK; tải lại đúng hai tệp được hỗ trợ.",
                ) from None
            finally:
                with contextlib.suppress(Exception):
                    await task
                shutil.rmtree(temporary, ignore_errors=True)
        work = Path(tempfile.mkdtemp(prefix="rd-cloud-"))
        command = [
            "java",
            "-Xmx512m",
            "-Dorg.slf4j.simpleLogger.defaultLogLevel=off",
            "-cp",
            self.classpath,
            "local.rangdong.NativeProbe",
            "--worker",
            str(prepared / "base.apk"),
            str(prepared / "libs"),
            str(prepared / "app-credentials"),
        ]
        try:
            self.process = await asyncio.create_subprocess_exec(
                *command,
                cwd=work,
                env={
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "HOME": str(work),
                    "LANG": "C.UTF-8",
                },
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=MAX_WORKER_BYTES + 1,
            )
            async with asyncio.timeout(240):
                self.process.stdin.write(json.dumps(credentials).encode() + b"\n")
                await self.process.stdin.drain()
                self.process.stdin.close()
                credentials.clear()
                output = await self.process.stdout.readuntil(b"\n")
                if len(output) > MAX_WORKER_BYTES:
                    raise HelperError(
                        "cloud_result_too_large", "Danh sách thiết bị quá lớn."
                    )
                await self.process.wait()
            result = json.loads(output)
            output = b""
            if self.process.returncode or not isinstance(result, dict):
                raise HelperError(
                    "cloud_worker_failed",
                    "Worker cloud không khởi động hoặc trả dữ liệu lỗi.",
                )
            if result.get("success") is not True:
                code = str(result.get("error", "")).upper()
                if code == "USER_PASSWD_WRONG":
                    raise HelperError(
                        "cloud_login_rejected",
                        "Cloud từ chối đăng nhập. Kiểm tra đúng email/số điện thoại và mật khẩu Rạng Đông; không phải mật khẩu Google.",
                    )
                if any(
                    term in code for term in ("MFA", "CAPTCHA", "VALIDATE", "VERIFY")
                ):
                    raise HelperError(
                        "cloud_verification_required",
                        "Tài khoản yêu cầu xác minh. Hoàn thành trong app Rạng Đông chính thức; add-on không bỏ qua MFA/CAPTCHA.",
                    )
                raise HelperError(
                    "cloud_request_failed",
                    "Cloud từ chối yêu cầu hoặc cấu trúc dữ liệu chưa được hỗ trợ. Không tự thử lại.",
                )
            devices = result.get("devices")
            if not isinstance(devices, list):
                raise HelperError(
                    "cloud_invalid_result", "Danh sách thiết bị cloud không hợp lệ."
                )
            return devices
        except HelperError:
            raise
        except TimeoutError:
            raise HelperError(
                "cloud_timeout", "Cloud không hoàn tất trong 240 giây; worker đã dừng."
            ) from None
        except (
            OSError,
            ValueError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ):
            raise HelperError(
                "cloud_worker_failed",
                "Không chạy được worker cloud; kiểm tra APK, mạng và bộ nhớ máy.",
            ) from None
        finally:
            credentials.clear()
            await self.stop()
            shutil.rmtree(work, ignore_errors=True)

    async def stop(self) -> None:
        if self.process is not None:
            if self.process.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    self.process.kill()
            await self.process.wait()
            self.process = None
