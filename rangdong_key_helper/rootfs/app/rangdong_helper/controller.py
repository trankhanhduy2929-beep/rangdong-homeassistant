"""Coordinate ADB, Frida and the Home Assistant one-time bridge."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any

from .adb import AdbClient
from .bridge import HomeAssistantBridge
from .cloud import CloudClient
from .constants import DEFAULT_ADB_PORT, DEFAULT_PACKAGE_NAME, FRIDA_LOCAL_PORT
from .errors import HelperError
from .frida_client import FridaClient
from .installer import FridaInstaller
from .validation import (
    AndroidTarget,
    LoginCredentials,
    normalize_host,
    normalize_package,
    normalize_port,
    validate_records,
)


@dataclass(frozen=True, slots=True)
class AddonOptions:
    """Non-secret defaults stored in the add-on options file."""

    android_host: str = ""
    adb_port: int = DEFAULT_ADB_PORT
    package_name: str = DEFAULT_PACKAGE_NAME

    @classmethod
    def load(cls, path: Path = Path("/data/options.json")) -> AddonOptions:
        """Read options while tolerating a first run outside Supervisor."""

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}

        host = str(raw.get("android_host") or "").strip()
        if host:
            try:
                host = normalize_host(host)
            except HelperError:
                host = ""
        try:
            port = normalize_port(raw.get("adb_port", DEFAULT_ADB_PORT), "ADB port")
        except HelperError:
            port = DEFAULT_ADB_PORT
        try:
            package_name = normalize_package(
                raw.get("package_name", DEFAULT_PACKAGE_NAME)
            )
        except HelperError:
            package_name = DEFAULT_PACKAGE_NAME
        return cls(host, port, package_name)


@dataclass(frozen=True, slots=True)
class PreparedDevice:
    """A phone ready for Frida RPC."""

    serial: str
    abi: str
    process_id: int


class HelperController:
    """Expose high-level, serialized helper operations."""

    def __init__(
        self,
        *,
        options: AddonOptions | None = None,
        adb: AdbClient | None = None,
        installer: FridaInstaller | None = None,
        frida_client: FridaClient | None = None,
        bridge: HomeAssistantBridge | None = None,
        cloud: CloudClient | None = None,
    ) -> None:
        """Initialize helper dependencies."""

        self.options = options or AddonOptions.load()
        self._adb = adb or AdbClient()
        self._installer = installer or FridaInstaller()
        self._frida = frida_client or FridaClient()
        self._bridge = bridge or HomeAssistantBridge()
        self._cloud = cloud or CloudClient()
        self._operation_lock = asyncio.Lock()
        self._stage = "idle"
        self._last_error: str | None = None
        self._last_devices: list[dict[str, str | None]] = []
        self._active_serial: str | None = None

    def status(self) -> dict[str, Any]:
        """Return non-secret UI state."""

        return {
            "success": True,
            "busy": self._operation_lock.locked(),
            "stage": self._stage,
            "last_error": self._last_error,
            "devices": self._last_devices,
            "cloud": self._cloud.status(),
            "defaults": {
                "host": self.options.android_host,
                "adb_port": self.options.adb_port,
                "package_name": self.options.package_name,
            },
        }

    async def pair(self, host: str, pairing_port: int, code: str) -> dict[str, Any]:
        """Pair Android Wireless debugging."""

        async with self._exclusive_operation("pairing"):
            result = await self._adb.pair(host, pairing_port, code)
            self._stage = "paired"
            return {"success": True, **result}

    async def upload_cloud_apk(self, kind: str, stream: Any) -> dict[str, Any]:
        async with self._exclusive_operation("uploading_apk"):
            await self._cloud.upload(kind, stream)
            self._stage = "idle"
            return {
                "success": True,
                "cloud": self._cloud.status(),
                "message": "APK hợp lệ, đã lưu riêng trong add-on.",
            }

    async def clear_cloud_assets(self) -> dict[str, Any]:
        async with self._exclusive_operation("clearing_apk"):
            await self._cloud.clear_assets()
            self._stage = "idle"
            return {
                "success": True,
                "cloud": self._cloud.status(),
                "message": "Đã xóa APK nhập tay và cache. Bản tích hợp sẵn vẫn dùng được.",
            }

    async def cloud_scan(self, credentials: dict[str, str]) -> dict[str, Any]:
        try:
            async with self._exclusive_operation("cloud_login"):
                raw_records = await self._cloud.collect(credentials)
                records = validate_records(raw_records)
                raw_records.clear()
                if not records:
                    raise HelperError(
                        "no_local_keys",
                        "Đăng nhập được nhưng tài khoản không có thiết bị trả local key hợp lệ.",
                    )
                try:
                    self._stage = "importing"
                    bridge_result = await self._bridge.import_records(records)
                    self._last_devices = [record.masked() for record in records]
                    self._stage = "complete"
                    return {
                        "success": True,
                        "count": len(records),
                        "devices": self._last_devices,
                        "available_count": bridge_result.get("available_count"),
                        "message": "Đã lấy và chuyển key vào Home Assistant. Mở Rạng Đông Smart → LAN → Key Helper / bridge để chọn thiết bị.",
                    }
                finally:
                    records.clear()
        finally:
            credentials.clear()

    async def prepare(self, target: AndroidTarget) -> dict[str, Any]:
        """Prepare root Frida access and verify the SDK process."""

        async with self._exclusive_operation("preparing"):
            prepared = await self._prepare_locked(target)
            try:
                self._stage = "ready"
                return {
                    "success": True,
                    "serial": prepared.serial,
                    "abi": prepared.abi,
                    "process_id": prepared.process_id,
                    "frida_endpoint": f"127.0.0.1:{FRIDA_LOCAL_PORT}",
                    "message": "Kết nối điện thoại và ThingClips SDK thành công.",
                }
            finally:
                await self._close_frida(prepared.serial)

    async def scan(
        self,
        target: AndroidTarget,
        credentials: LoginCredentials | None,
    ) -> dict[str, Any]:
        """Collect keys and import them into the Home Assistant bridge."""

        async with self._exclusive_operation("preparing"):
            prepared = await self._prepare_locked(target)
            self._stage = "reading_app"
            try:
                raw_records = await self._frida.collect(
                    prepared.process_id,
                    credentials,
                )
                records = validate_records(raw_records)
                raw_records = None
                if not records:
                    raise HelperError(
                        "no_local_keys",
                        "Không tìm thấy local key 16-byte trong tài khoản/app hiện tại.",
                    )

                self._stage = "importing"
                bridge_result = await self._bridge.import_records(records)
                masked_devices = [record.masked() for record in records]
                records.clear()
                self._last_devices = masked_devices
                self._stage = "complete"
                return {
                    "success": True,
                    "count": len(masked_devices),
                    "devices": masked_devices,
                    "available_count": bridge_result.get("available_count"),
                    "message": (
                        "Đã import key vào Rạng Đông Smart. "
                        "Mở Add integration và chọn Android bridge."
                    ),
                }
            finally:
                await self._close_frida(prepared.serial)

    async def clear_bridge(self) -> dict[str, Any]:
        """Clear the Home Assistant bridge and local masked metadata."""

        async with self._exclusive_operation("clearing"):
            result = await self._bridge.clear()
            self._last_devices = []
            self._stage = "idle"
            return {
                "success": True,
                "devices": result.get("devices", []),
                "message": "Đã xóa các key tạm khỏi bridge.",
            }

    async def cleanup(self) -> None:
        """Remove the ADB port forward when the add-on stops normally."""

        await self._cloud.stop()
        if self._active_serial:
            await self._close_frida(self._active_serial)

    async def _prepare_locked(self, target: AndroidTarget) -> PreparedDevice:
        self._stage = "connecting_adb"
        serial = await self._adb.connect(target)
        self._active_serial = serial
        try:
            self._stage = "checking_root"
            await self._adb.require_root(serial)
            await self._adb.require_package(serial, target.package_name)
            abi = await self._adb.get_abi(serial)

            self._stage = "downloading_frida"
            server = await self._installer.get_server(abi)
            self._stage = "starting_frida"
            await self._adb.install_frida_server(
                serial,
                server.path,
                server.sha256,
            )
            await self._adb.start_frida_server(serial)

            self._stage = "starting_app"
            process_id = await self._adb.start_app(serial, target.package_name)
            self._stage = "checking_sdk"
            await self._frida.probe(process_id)
            return PreparedDevice(serial, abi, process_id)
        except BaseException:
            await self._close_frida(serial)
            raise

    async def _close_frida(self, serial: str) -> None:
        try:
            await self._adb.remove_forward(serial)
        finally:
            await self._adb.stop_frida_server(serial)

    def _exclusive_operation(self, stage: str) -> _OperationContext:
        return _OperationContext(self, stage)


class _OperationContext:
    """Set controller stage and expose only one sensitive operation at a time."""

    def __init__(self, controller: HelperController, stage: str) -> None:
        self._controller = controller
        self._stage = stage

    async def __aenter__(self) -> None:
        if self._controller._operation_lock.locked():
            raise HelperError(
                "operation_busy",
                "Một thao tác khác đang chạy. Hãy chờ hoàn tất.",
                status=409,
            )
        await self._controller._operation_lock.acquire()
        self._controller._stage = self._stage
        self._controller._last_error = None

    async def __aexit__(
        self,
        error_type: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if isinstance(error, HelperError):
            self._controller._last_error = error.code
            self._controller._stage = "error"
        elif error is not None:
            self._controller._last_error = "internal_error"
            self._controller._stage = "error"
        self._controller._operation_lock.release()
