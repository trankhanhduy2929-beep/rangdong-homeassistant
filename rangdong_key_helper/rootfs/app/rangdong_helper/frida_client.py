"""Load the bundled Frida agent into the user's Rạng Đông app."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .constants import FRIDA_LOCAL_PORT
from .errors import HelperError
from .validation import LoginCredentials


class FridaClient:
    """Perform bounded, one-shot RPC calls against the Android app process."""

    def __init__(self, agent_path: Path | None = None) -> None:
        """Load the static compiled agent source."""

        if agent_path is None:
            agent_path = Path(__file__).with_name("frida_agent.js")
        self._agent_source = agent_path.read_text(encoding="utf-8")

    async def probe(self, process_id: int) -> dict[str, Any]:
        """Verify that Frida and the ThingClips Java classes are available."""

        return await self._run_rpc("ping", process_id, timeout=35)

    async def collect(
        self,
        process_id: int,
        credentials: LoginCredentials | None,
    ) -> list[dict[str, Any]]:
        """Optionally log in, then return candidate device records."""

        return await self._run_rpc(
            "collect",
            process_id,
            credentials=credentials,
            timeout=95,
        )

    async def _run_rpc(
        self,
        operation: str,
        process_id: int,
        *,
        credentials: LoginCredentials | None = None,
        timeout: float,
    ) -> Any:
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self._run_rpc_sync,
                    operation,
                    process_id,
                    credentials,
                ),
                timeout=timeout,
            )
        except HelperError:
            raise
        except TimeoutError as error:
            raise HelperError(
                "frida_timeout",
                "Frida hoặc ứng dụng Rạng Đông không phản hồi đúng thời gian.",
            ) from error
        except Exception as error:
            raise HelperError(
                "frida_rpc_failed",
                "Không điều khiển được SDK trong ứng dụng Rạng Đông.",
            ) from error

    def _run_rpc_sync(
        self,
        operation: str,
        process_id: int,
        credentials: LoginCredentials | None,
    ) -> Any:
        try:
            import frida
        except ImportError as error:
            raise HelperError(
                "frida_missing",
                "Thư viện Frida chưa được cài trong add-on.",
                status=500,
            ) from error

        manager = frida.get_device_manager()
        device = manager.add_remote_device(f"127.0.0.1:{FRIDA_LOCAL_PORT}")
        session = device.attach(process_id)
        script = session.create_script(self._agent_source, name="rangdong-key-helper")
        script_errors: list[str] = []

        def on_message(message: dict[str, Any], _data: bytes | None) -> None:
            if message.get("type") == "error":
                description = str(message.get("description") or "agent error")
                script_errors.append(description[:160])

        script.on("message", on_message)
        try:
            script.load()
            exports = script.exports_sync
            if operation == "ping":
                result = exports.ping()
                if not isinstance(result, dict) or not result.get("ok"):
                    raise HelperError(
                        "thingclips_sdk_missing",
                        "Không tìm thấy ThingClips SDK trong process của app Rạng Đông.",
                    )
                return result

            if credentials is not None:
                login_result = exports.login(
                    credentials.country_code,
                    credentials.phone,
                    credentials.password,
                )
                if not isinstance(login_result, dict) or not login_result.get("ok"):
                    code = ""
                    message = "Đăng nhập Rạng Đông thất bại."
                    if isinstance(login_result, dict):
                        code = str(login_result.get("code") or "")[:64]
                        sdk_message = str(login_result.get("message") or "").strip()
                        if sdk_message:
                            message = sdk_message[:240]
                    suffix = f" ({code})" if code else ""
                    raise HelperError("rangdong_login_failed", f"{message}{suffix}")

            status = exports.status()
            result = exports.collect()
            if (
                not isinstance(status, dict) or not status.get("logged_in")
            ) and not result:
                raise HelperError(
                    "app_not_logged_in",
                    "App Rạng Đông chưa đăng nhập. Dùng nút Đăng nhập & dò hoặc đăng nhập trên điện thoại.",
                )
            if script_errors:
                raise HelperError(
                    "frida_agent_failed",
                    "Frida agent gặp lỗi khi đọc dữ liệu ứng dụng.",
                )
            return result
        finally:
            try:
                script.unload()
            finally:
                session.detach()
