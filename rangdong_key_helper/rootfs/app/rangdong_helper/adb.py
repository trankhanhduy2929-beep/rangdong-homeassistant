"""Asynchronous ADB operations for one user-controlled Android device."""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path
from shutil import which

from .constants import (
    FRIDA_LOCAL_PORT,
    FRIDA_PID_PATH,
    FRIDA_REMOTE_PATH,
    FRIDA_REMOTE_PORT,
)
from .errors import HelperError
from .validation import AndroidTarget


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Captured output from a command that contains no secret arguments."""

    stdout: str
    stderr: str
    returncode: int


class AdbClient:
    """Run ADB without invoking a local shell."""

    def __init__(self, *, home: Path = Path("/data")) -> None:
        """Initialize the ADB process environment."""

        self._environment = {
            **os.environ,
            "HOME": str(home),
            "LC_ALL": "C.UTF-8",
        }
        self._root_modes: dict[str, tuple[str, ...]] = {}

    async def pair(self, host: str, port: int, code: str) -> dict[str, str]:
        """Pair with Android Wireless debugging without exposing the code in argv."""

        serial = _network_serial(host, port)
        result = await self._run(
            ["pair", serial],
            input_data=f"{code}\n".encode(),
            timeout=35,
        )
        output = f"{result.stdout}\n{result.stderr}".lower()
        if result.returncode or "successfully paired" not in output:
            raise HelperError(
                "adb_pair_failed",
                "Không ghép đôi được. Kiểm tra IP, cổng ghép đôi và mã 6 số.",
            )
        return {"serial": serial, "message": "Ghép đôi ADB thành công."}

    async def connect(self, target: AndroidTarget) -> str:
        """Connect ADB and require the target to be authorized."""

        await self._run_checked(["start-server"], "adb_start_failed", timeout=20)
        result = await self._run(["connect", target.serial], timeout=25)
        output = f"{result.stdout}\n{result.stderr}".lower()
        if result.returncode or any(
            marker in output
            for marker in ("failed", "cannot", "unable", "refused", "timed out")
        ):
            raise HelperError(
                "adb_connect_failed",
                "Không kết nối được ADB. Kiểm tra cổng Kết nối không dây trên điện thoại.",
            )

        devices = await self._run_checked(
            ["devices"],
            "adb_devices_failed",
            timeout=15,
        )
        state = _device_state(devices.stdout, target.serial)
        if state == "unauthorized":
            raise HelperError(
                "adb_unauthorized",
                "Điện thoại chưa cho phép ADB. Hãy xác nhận hộp thoại trên điện thoại.",
            )
        if state != "device":
            raise HelperError(
                "adb_not_ready",
                "Điện thoại chưa ở trạng thái ADB sẵn sàng.",
            )
        return target.serial

    async def require_root(self, serial: str) -> None:
        """Require a working root shell on the phone."""

        for mode in (
            ("su", "-c"),
            ("su", "0", "sh", "-c"),
        ):
            arguments = ["-s", serial, "shell", *mode, "id"]
            result = await self._run(arguments, timeout=15)
            if result.returncode == 0 and "uid=0" in result.stdout:
                self._root_modes[serial] = mode
                return
        raise HelperError(
            "root_required",
            "Điện thoại phải root và ứng dụng quản lý root phải cấp quyền cho shell ADB.",
        )

    async def require_package(self, serial: str, package_name: str) -> None:
        """Require the Rạng Đông app package to be installed."""

        result = await self._run(
            ["-s", serial, "shell", "pm", "path", package_name],
            timeout=15,
        )
        if result.returncode or not result.stdout.strip().startswith("package:"):
            raise HelperError(
                "app_not_installed",
                f"Không tìm thấy ứng dụng Android {package_name}.",
            )

    async def get_abi(self, serial: str) -> str:
        """Return the primary Android ABI."""

        result = await self._run_checked(
            ["-s", serial, "shell", "getprop", "ro.product.cpu.abi"],
            "abi_detection_failed",
            timeout=15,
        )
        abi = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if not abi:
            raise HelperError(
                "abi_detection_failed", "Không đọc được CPU ABI của điện thoại."
            )
        return abi

    async def install_frida_server(
        self,
        serial: str,
        local_path: Path,
        expected_sha256: str,
    ) -> None:
        """Push a verified Frida server to the private helper path."""

        remote_sha256 = await self._remote_file_sha256(serial, FRIDA_REMOTE_PATH)
        if remote_sha256 != expected_sha256:
            await self.stop_frida_server(serial)
            await self._run_checked(
                ["-s", serial, "push", str(local_path), FRIDA_REMOTE_PATH],
                "frida_push_failed",
                timeout=120,
            )
        await self._run_checked(
            ["-s", serial, "shell", "chmod", "700", FRIDA_REMOTE_PATH],
            "frida_chmod_failed",
            timeout=15,
        )
        remote_sha256 = await self._remote_file_sha256(serial, FRIDA_REMOTE_PATH)
        if remote_sha256 != expected_sha256:
            raise HelperError(
                "frida_remote_checksum_failed",
                "Checksum Frida server trên điện thoại không khớp.",
            )

    async def start_frida_server(self, serial: str) -> None:
        """Start the helper Frida server bound only to Android loopback."""

        check = await self._run(
            self._root_arguments(
                serial,
                (
                    f"test -f {FRIDA_PID_PATH} && pid=$(cat {FRIDA_PID_PATH}) && "
                    f'test "$(readlink /proc/$pid/exe 2>/dev/null)" = '
                    f'"{FRIDA_REMOTE_PATH}" && kill -0 $pid 2>/dev/null'
                ),
            ),
            timeout=12,
        )
        if check.returncode:
            command = (
                f"nohup {FRIDA_REMOTE_PATH} -l 127.0.0.1:{FRIDA_REMOTE_PORT} "
                f">/dev/null 2>&1 & echo $! > {FRIDA_PID_PATH}"
            )
            result = await self._run(
                self._root_arguments(serial, command),
                timeout=20,
            )
            if result.returncode:
                raise HelperError(
                    "frida_start_failed",
                    "Không khởi động được Frida server bằng quyền root.",
                )

        await self._run(
            ["-s", serial, "forward", "--remove", f"tcp:{FRIDA_LOCAL_PORT}"],
            timeout=10,
        )
        await self._run_checked(
            [
                "-s",
                serial,
                "forward",
                f"tcp:{FRIDA_LOCAL_PORT}",
                f"tcp:{FRIDA_REMOTE_PORT}",
            ],
            "frida_forward_failed",
            timeout=15,
        )
        await asyncio.sleep(1)

    async def stop_frida_server(self, serial: str) -> None:
        """Stop only the Frida server process started by this helper."""

        command = (
            f"if test -f {FRIDA_PID_PATH}; then "
            f"pid=$(cat {FRIDA_PID_PATH}); "
            f'if test "$(readlink /proc/$pid/exe 2>/dev/null)" = '
            f'"{FRIDA_REMOTE_PATH}"; then kill $pid 2>/dev/null || true; fi; '
            f"rm -f {FRIDA_PID_PATH}; fi"
        )
        result = await self._run(
            self._root_arguments(serial, command),
            timeout=15,
        )
        if result.returncode:
            raise HelperError(
                "frida_stop_failed",
                "Không dừng được Frida server trên điện thoại.",
            )

    async def start_app(self, serial: str, package_name: str) -> int:
        """Launch the app if needed and return its main process ID."""

        pid = await self._get_pid(serial, package_name)
        if pid is None:
            result = await self._run(
                [
                    "-s",
                    serial,
                    "shell",
                    "monkey",
                    "-p",
                    package_name,
                    "-c",
                    "android.intent.category.LAUNCHER",
                    "1",
                ],
                timeout=25,
            )
            if result.returncode:
                raise HelperError(
                    "app_start_failed",
                    "Không mở được ứng dụng Rạng Đông trên điện thoại.",
                )
            for _ in range(20):
                await asyncio.sleep(0.5)
                pid = await self._get_pid(serial, package_name)
                if pid is not None:
                    break
        if pid is None:
            raise HelperError(
                "app_process_missing",
                "Ứng dụng Rạng Đông không chạy hoặc đã chặn môi trường root/Frida.",
            )
        return pid

    async def remove_forward(self, serial: str) -> None:
        """Remove the local-only Frida tunnel."""

        await self._run(
            ["-s", serial, "forward", "--remove", f"tcp:{FRIDA_LOCAL_PORT}"],
            timeout=10,
        )

    async def _get_pid(self, serial: str, package_name: str) -> int | None:
        result = await self._run(
            ["-s", serial, "shell", "pidof", package_name],
            timeout=10,
        )
        if result.returncode:
            return None
        for item in result.stdout.split():
            if item.isdigit():
                return int(item)
        return None

    async def _remote_file_sha256(self, serial: str, path: str) -> str | None:
        command = f"test -x {path} && sha256sum {path}"
        result = await self._run(
            self._root_arguments(serial, command),
            timeout=90,
        )
        digest = result.stdout.strip().split(maxsplit=1)[0]
        if result.returncode == 0 and re.fullmatch(r"[a-f0-9]{64}", digest):
            return digest
        return None

    def _root_arguments(self, serial: str, command: str) -> list[str]:
        mode = self._root_modes.get(serial, ("su", "-c"))
        return ["-s", serial, "shell", *mode, command]

    async def _run_checked(
        self,
        arguments: list[str],
        code: str,
        *,
        timeout: float,
    ) -> CommandResult:
        result = await self._run(arguments, timeout=timeout)
        if result.returncode:
            raise HelperError(code, _safe_command_error(result))
        return result

    async def _run(
        self,
        arguments: list[str],
        *,
        input_data: bytes | None = None,
        timeout: float,
    ) -> CommandResult:
        if which("adb") is None:
            raise HelperError(
                "adb_missing", "ADB chưa được cài trong add-on.", status=500
            )
        process = await asyncio.create_subprocess_exec(
            "adb",
            *arguments,
            stdin=asyncio.subprocess.PIPE if input_data is not None else None,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self._environment,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input_data),
                timeout=timeout,
            )
        except TimeoutError as error:
            process.kill()
            await process.communicate()
            raise HelperError(
                "adb_timeout", "ADB không phản hồi đúng thời gian."
            ) from error
        return CommandResult(
            stdout.decode("utf-8", "replace"),
            stderr.decode("utf-8", "replace"),
            process.returncode or 0,
        )


def _network_serial(host: str, port: int) -> str:
    """Format an IPv4, IPv6 or hostname endpoint for ADB."""

    if ":" in host and not host.startswith("["):
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def _device_state(output: str, serial: str) -> str | None:
    """Extract one serial's state from `adb devices`."""

    for line in output.splitlines():
        fields = line.strip().split()
        if len(fields) >= 2 and fields[0] == serial:
            return fields[1]
    return None


def _safe_command_error(result: CommandResult) -> str:
    """Return short command output without including argv or request data."""

    message = result.stderr.strip() or result.stdout.strip()
    message = " ".join(message.split())[:240]
    return message or "Lệnh ADB thất bại."
