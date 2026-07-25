"""Browser-bridge contract helpers + CORS smoke (no scoring)."""

from __future__ import annotations

import json
import tempfile
import unittest
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread

from mbm.live.prizepicks_http import PATH_CAPTURE, create_handler
from mbm.providers.prizepicks.service import PrizePicksCaptureService

ROOT = Path(__file__).resolve().parents[1]
FIX_OK = ROOT / "fixtures" / "prizepicks" / "synthetic" / "board_ok.json"


class TestPrizePicksBrowserBridge(unittest.TestCase):
    def test_cors_preflight_and_omit_credentials_headers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            svc = PrizePicksCaptureService(Path(tmp), bridge_token="t")
            handler = create_handler(svc)
            from http.server import ThreadingHTTPServer

            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            port = server.server_address[1]
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                conn = HTTPConnection("127.0.0.1", port, timeout=5)
                conn.request(
                    "OPTIONS",
                    PATH_CAPTURE,
                    headers={
                        "Origin": "https://app.prizepicks.com",
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "content-type,x-mbm-bridge-token",
                    },
                )
                pre = conn.getresponse()
                pre.read()
                self.assertEqual(pre.status, 204)
                self.assertEqual(pre.getheader("Access-Control-Allow-Origin"), "https://app.prizepicks.com")
                allow = (pre.getheader("Access-Control-Allow-Headers") or "").lower()
                self.assertIn("x-mbm-bridge-token", allow)
                self.assertIn("content-type", allow)

                payload = json.loads(FIX_OK.read_text(encoding="utf-8"))
                payload.pop("_fixture_meta", None)
                body = json.dumps(
                    {
                        "source": "prizepicks_browser_bridge",
                        "captured_at": "2026-07-24T06:00:00Z",
                        "authoritative_capture": False,
                        "payload": payload,
                    }
                ).encode("utf-8")
                conn.request(
                    "POST",
                    PATH_CAPTURE,
                    body=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-MBM-Bridge-Token": "t",
                        "Origin": "https://app.prizepicks.com",
                        "Content-Length": str(len(body)),
                        # Must not require Cookie on MBM side.
                    },
                )
                resp = conn.getresponse()
                raw = resp.read().decode("utf-8")
                data = json.loads(raw)
                self.assertEqual(resp.status, 200)
                self.assertEqual(data["status"], "CAPTURED")
                self.assertEqual(data["cleared_status"], "NOT_CLEARED")
                self.assertFalse(data["authoritative_capture"])
                self.assertFalse(data["scoring_touched"])
                self.assertEqual(
                    resp.getheader("Access-Control-Allow-Origin"),
                    "https://app.prizepicks.com",
                )
                conn.close()
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
