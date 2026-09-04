"""Ingress-only HTTP API for the Rạng Đông key helper."""

from __future__ import annotations

import html
import json
import logging
import secrets
from ipaddress import ip_address
from typing import Any

from aiohttp import web

from .authorization import HomeAssistantUserAuthorizer
from .constants import ADDON_PORT, MAX_REQUEST_BYTES
from .controller import HelperController
from .errors import HelperError
from .page import PAGE_TEMPLATE
from .validation import (
    normalize_host,
    normalize_pairing_code,
    normalize_port,
    parse_login,
    parse_target,
)

_LOGGER = logging.getLogger(__name__)


def create_app(
    controller: HelperController | None = None,
    authorizer: HomeAssistantUserAuthorizer | None = None,
) -> web.Application:
    """Create the add-on application."""

    helper = controller or HelperController()
    user_authorizer = authorizer or HomeAssistantUserAuthorizer()
    csrf_token = secrets.token_urlsafe(32)

    @web.middleware
    async def ingress_only(
        request: web.Request,
        handler: Any,
    ) -> web.StreamResponse:
        if request.path != "/health" and (
            not _is_ingress_remote(request.remote)
            or request.headers.get("X-Hass-Source") != "core.ingress"
            or not request.headers.get("X-Ingress-Path", "").startswith(
                "/api/hassio_ingress/"
            )
        ):
            raise web.HTTPForbidden(text="Ingress access only")
        if request.path != "/health":
            await user_authorizer.require_admin(
                request.headers.get("X-Remote-User-Id", "")
            )
        return await handler(request)

    @web.middleware
    async def handle_errors(
        request: web.Request,
        handler: Any,
    ) -> web.StreamResponse:
        try:
            if (
                request.method in {"POST", "PUT", "PATCH", "DELETE"}
                and request.headers.get("X-CSRF-Token") != csrf_token
            ):
                raise HelperError(
                    "csrf_failed",
                    "Phiên Ingress không hợp lệ. Hãy tải lại trang.",
                    status=403,
                )
            return await handler(request)
        except HelperError as error:
            return web.json_response(
                {
                    "success": False,
                    "error": error.code,
                    "message": error.message,
                },
                status=error.status,
            )
        except web.HTTPException:
            raise
        except Exception:
            _LOGGER.exception("Unexpected helper failure")
            return web.json_response(
                {
                    "success": False,
                    "error": "internal_error",
                    "message": "Add-on gặp lỗi nội bộ.",
                },
                status=500,
            )

    @web.middleware
    async def security_headers(
        request: web.Request,
        handler: Any,
    ) -> web.StreamResponse:
        response = await handler(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        return response

    app = web.Application(
        client_max_size=MAX_REQUEST_BYTES,
        middlewares=[security_headers, handle_errors, ingress_only],
    )

    async def index(_request: web.Request) -> web.Response:
        nonce = secrets.token_urlsafe(18)
        defaults = helper.status()["defaults"]
        page = PAGE_TEMPLATE.replace("__NONCE__", html.escape(nonce, quote=True))
        page = page.replace("__CSRF_JSON__", _safe_json(csrf_token))
        page = page.replace("__CONFIG_JSON__", _safe_json(defaults))
        response = web.Response(text=page, content_type="text/html")
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            f"style-src 'nonce-{nonce}'; script-src 'nonce-{nonce}'; "
            "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'self'"
        )
        return response

    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"success": True})

    async def status(_request: web.Request) -> web.Response:
        return web.json_response(helper.status())

    async def pair(request: web.Request) -> web.Response:
        payload = await _read_payload(request)
        host = normalize_host(payload.get("host"))
        port = normalize_port(payload.get("pairing_port"), "Cổng ghép đôi")
        code = normalize_pairing_code(payload.get("pairing_code"))
        payload["pairing_code"] = None
        return web.json_response(await helper.pair(host, port, code))

    async def prepare(request: web.Request) -> web.Response:
        payload = await _read_payload(request)
        target = parse_target(
            payload,
            default_host=helper.options.android_host,
            default_port=helper.options.adb_port,
            default_package=helper.options.package_name,
        )
        return web.json_response(await helper.prepare(target))

    async def scan(request: web.Request) -> web.Response:
        payload = await _read_payload(request)
        target = parse_target(
            payload,
            default_host=helper.options.android_host,
            default_port=helper.options.adb_port,
            default_package=helper.options.package_name,
        )
        return web.json_response(await helper.scan(target, None))

    async def login_scan(request: web.Request) -> web.Response:
        payload = await _read_payload(request)
        target = parse_target(
            payload,
            default_host=helper.options.android_host,
            default_port=helper.options.adb_port,
            default_package=helper.options.package_name,
        )
        credentials = parse_login(payload)
        payload["password"] = None
        try:
            return web.json_response(await helper.scan(target, credentials))
        finally:
            credentials = None

    async def clear_bridge(_request: web.Request) -> web.Response:
        return web.json_response(await helper.clear_bridge())

    async def cleanup(_app: web.Application) -> None:
        await helper.cleanup()

    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/api/status", status)
    app.router.add_post("/api/pair", pair)
    app.router.add_post("/api/prepare", prepare)
    app.router.add_post("/api/scan", scan)
    app.router.add_post("/api/login-scan", login_scan)
    app.router.add_delete("/api/bridge", clear_bridge)
    app.on_cleanup.append(cleanup)
    return app


async def _read_payload(request: web.Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HelperError("invalid_json", "Dữ liệu gửi lên không hợp lệ.") from error
    if not isinstance(payload, dict):
        raise HelperError("invalid_json", "Dữ liệu gửi lên phải là object JSON.")
    return payload


def _is_ingress_remote(remote: str | None) -> bool:
    if remote is None:
        return False
    try:
        address = ip_address(remote)
    except ValueError:
        return False
    return address.is_loopback or str(address) == "172.30.32.2"


def _safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c"
    )


def main() -> None:
    """Run the Ingress server."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    web.run_app(
        create_app(),
        host="0.0.0.0",
        port=ADDON_PORT,
        access_log=None,
        print=None,
    )
