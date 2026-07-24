"""Stdlib HTTP server for the analyst dashboard.

Imports only analyst snapshot/models + render — no CS2 adapter types.
"""

from __future__ import annotations

import json
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import unquote, urlparse

from mbm.analyst.models import DashboardSnapshot
from mbm.dashboard.render import (
    render_board,
    render_calibration,
    render_not_found,
    render_pick,
    render_settlement,
)


class DashboardHandler(BaseHTTPRequestHandler):
    snapshot_provider: Callable[[], DashboardSnapshot] = staticmethod(
        lambda: (_ for _ in ()).throw(RuntimeError("snapshot provider unset"))
    )

    def log_message(self, fmt: str, *args) -> None:  # quieter local runs
        pass

    def _send(self, code: int, body: str, content_type: str = "text/html; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        snapshot = type(self).snapshot_provider()
        path = urlparse(self.path).path
        if path == "/health":
            self._send(200, json.dumps({"ok": True, "core_ready": snapshot.core_ready}), "application/json")
            return
        if path == "/api/snapshot":
            self._send(200, json.dumps(snapshot.to_dict(), default=str), "application/json")
            return
        if path in {"/", "/board"}:
            self._send(200, render_board(snapshot))
            return
        if path == "/settlement":
            self._send(200, render_settlement(snapshot))
            return
        if path == "/calibration":
            self._send(200, render_calibration(snapshot))
            return
        if path.startswith("/pick/"):
            pick_id = unquote(path[len("/pick/") :])
            pick = snapshot.picks.get(pick_id)
            if pick is None:
                self._send(404, render_not_found(snapshot, f"Unknown pick: {pick_id}"))
                return
            self._send(200, render_pick(snapshot, pick))
            return
        self._send(404, render_not_found(snapshot, f"No route for {path}"))


def create_handler(snapshot: DashboardSnapshot) -> type[BaseHTTPRequestHandler]:
    return type(
        "BoundDashboardHandler",
        (DashboardHandler,),
        {"snapshot_provider": staticmethod(lambda: snapshot)},
    )


def serve_dashboard(
    snapshot: DashboardSnapshot,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> ThreadingHTTPServer:
    handler = create_handler(snapshot)
    server = ThreadingHTTPServer((host, port), handler)
    return server
