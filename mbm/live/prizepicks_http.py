"""Locked PrizePicks live routes. Do not rename paths."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from mbm.providers.prizepicks.sanitize import SensitivePayloadError
from mbm.providers.prizepicks.service import PrizePicksCaptureService

BRIDGE_TOKEN_HEADER = "X-MBM-Bridge-Token"

# Locked paths — do not rename.
PATH_CAPTURE = "/api/live/prizepicks/capture-board"
PATH_LATEST = "/api/live/prizepicks/board-snapshots/latest"
PATH_HISTORY = "/api/live/prizepicks/board-history"
PATH_HEALTH = "/api/live/prizepicks/health"

# Browser bridge may POST from the PrizePicks origin (response JSON only).
_CORS_ALLOW_HEADERS = "Content-Type, X-MBM-Bridge-Token"
_CORS_ALLOW_METHODS = "GET, POST, OPTIONS"


class PrizePicksHandler(BaseHTTPRequestHandler):
    service: PrizePicksCaptureService

    def log_message(self, fmt: str, *args: Any) -> None:
        pass

    def _cors_headers(self) -> None:
        origin = self.headers.get("Origin") or "*"
        # Reflect request Origin so credentialed browser POSTs are unnecessary;
        # bridge must use credentials:omit and only the bridge token header.
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", _CORS_ALLOW_METHODS)
        self.send_header("Access-Control-Allow-Headers", _CORS_ALLOW_HEADERS)
        self.send_header("Access-Control-Max-Age", "86400")

    def _send_json(self, code: int, body: dict[str, Any]) -> None:
        if "scoring_touched" not in body:
            body = {**body, "scoring_touched": False}
        data = json.dumps(body, default=str).encode("utf-8")
        self.send_response(code)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid JSON body: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def do_OPTIONS(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path not in {PATH_CAPTURE, PATH_LATEST, PATH_HISTORY, PATH_HEALTH}:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        svc = type(self).service
        if path == PATH_HEALTH:
            self._send_json(200, svc.health())
            return
        if path == PATH_LATEST:
            self._send_json(200, svc.latest_snapshot())
            return
        if path == PATH_HISTORY:
            self._send_json(200, svc.board_history())
            return
        self._send_json(404, {"error": f"No route for {path}", "scoring_touched": False})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != PATH_CAPTURE:
            self._send_json(404, {"error": f"No route for {path}", "scoring_touched": False})
            return
        svc = type(self).service
        try:
            svc.check_bridge_token(self.headers.get(BRIDGE_TOKEN_HEADER))
            body = self._read_json()
            result = svc.capture_board(body)
            self._send_json(200, result.to_dict())
        except PermissionError as exc:
            self._send_json(401, {"error": str(exc), "scoring_touched": False})
        except SensitivePayloadError as exc:
            self._send_json(400, {"error": str(exc), "scoring_touched": False})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc), "scoring_touched": False})


def create_handler(service: PrizePicksCaptureService) -> type[BaseHTTPRequestHandler]:
    return type(
        "BoundPrizePicksHandler",
        (PrizePicksHandler,),
        {"service": service},
    )


def serve_prizepicks(
    service: PrizePicksCaptureService,
    *,
    host: str = "127.0.0.1",
    port: int = 8770,
) -> ThreadingHTTPServer:
    handler = create_handler(service)
    server = ThreadingHTTPServer((host, port), handler)
    return server
