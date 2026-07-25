"""Acceptance tests for PrizePicks browser-bridge capture (scoring untouched)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from mbm.live.prizepicks_http import (
    PATH_CAPTURE,
    PATH_HEALTH,
    PATH_HISTORY,
    PATH_LATEST,
    create_handler,
)
from mbm.providers.prizepicks.sanitize import SensitivePayloadError, reject_sensitive_payload
from mbm.providers.prizepicks.service import HEALTH_FIELDS, PrizePicksCaptureService

ROOT = Path(__file__).resolve().parents[1]
FIX_OK = ROOT / "fixtures" / "prizepicks" / "synthetic" / "board_ok.json"
FIX_CS2 = ROOT / "fixtures" / "prizepicks" / "synthetic" / "board_cs2_only.json"


def _payload(path: Path) -> dict:
    body = json.loads(path.read_text(encoding="utf-8"))
    body.pop("_fixture_meta", None)
    return body


class TestPrizePicksCapture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.svc = PrizePicksCaptureService(self.root, bridge_token="test-token")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _capture(
        self,
        payload: dict,
        *,
        authoritative: bool = False,
        sports: list[str] | None = None,
        captured_at: str = "2026-07-24T00:00:00Z",
    ):
        body: dict = {
            "source": "prizepicks_browser_bridge",
            "captured_at": captured_at,
            "authoritative_capture": authoritative,
            "payload": payload,
        }
        if sports is not None:
            body["sports"] = sports
        return self.svc.capture_board(body)

    def test_one_capture_one_append_only_snapshot(self) -> None:
        r1 = self._capture(_payload(FIX_OK), captured_at="2026-07-24T00:00:00Z")
        r2 = self._capture(_payload(FIX_OK), captured_at="2026-07-24T00:01:00Z")
        self.assertEqual(r1.status, "CAPTURED")
        self.assertEqual(r2.status, "CAPTURED")
        self.assertNotEqual(r1.snapshot_id, r2.snapshot_id)
        hist = self.svc.board_history()
        self.assertEqual(hist["count"], 2)
        self.assertFalse(hist["scoring_touched"])
        raw_path = self.svc.store.snapshots_dir / f"{r1.snapshot_id}.json"
        original = raw_path.read_bytes()
        with self.assertRaises(ValueError):
            self.svc.store.write_normalized(r1.snapshot_id, [])
        self.assertEqual(raw_path.read_bytes(), original)

    def test_normalized_records_and_unresolved_identity(self) -> None:
        self._capture(_payload(FIX_OK))
        props = self.svc.active_props()
        self.assertGreaterEqual(len(props), 2)
        for p in props:
            self.assertEqual(p.identity_status, "unresolved")
            self.assertTrue(p.player_id)  # id from relationship, not name merge

    def test_non_authoritative_never_marks_removed(self) -> None:
        self._capture(_payload(FIX_OK), authoritative=False)
        # Second capture drops valorant prop from payload but non-authoritative
        self._capture(
            _payload(FIX_CS2),
            authoritative=False,
            sports=["cs2"],
            captured_at="2026-07-24T01:00:00Z",
        )
        props = {p.prop_id: p for p in self.svc.active_props()}
        self.assertIn("pp-val-1", props)
        self.assertEqual(props["pp-val-1"].status, "ACTIVE")
        self.assertNotEqual(props["pp-val-1"].status, "REMOVED")

    def test_scoped_cs2_authoritative_cannot_remove_valorant(self) -> None:
        self._capture(_payload(FIX_OK), authoritative=False)
        result = self._capture(
            _payload(FIX_CS2),
            authoritative=True,
            sports=["cs2"],
            captured_at="2026-07-24T02:00:00Z",
        )
        self.assertEqual(result.status, "CAPTURED")
        props = {p.prop_id: p for p in self.svc.active_props()}
        self.assertEqual(props["pp-val-1"].status, "ACTIVE")
        # Old cs2 prop absent from scoped authoritative capture may clear
        if "pp-cs2-1" in props:
            self.assertEqual(props["pp-cs2-1"].status, "REMOVED")

    def test_full_authoritative_can_clear(self) -> None:
        self._capture(_payload(FIX_OK), authoritative=False)
        result = self._capture(
            _payload(FIX_CS2),
            authoritative=True,
            sports=None,
            captured_at="2026-07-24T03:00:00Z",
        )
        self.assertEqual(result.cleared_status, "CLEARED")
        self.assertGreater(result.cleared_count, 0)
        props = {p.prop_id: p for p in self.svc.active_props()}
        self.assertEqual(props["pp-val-1"].status, "REMOVED")

    def test_sensitive_keys_rejected(self) -> None:
        with self.assertRaises(SensitivePayloadError):
            reject_sensitive_payload({"cookie": "x"})
        bad = {
            "source": "prizepicks_browser_bridge",
            "captured_at": "2026-07-24T00:00:00Z",
            "authoritative_capture": False,
            "payload": {"data": [], "authorization": "Bearer x"},
        }
        with self.assertRaises(SensitivePayloadError):
            self.svc.capture_board(bad)

    def test_health_eight_allowlisted_fields(self) -> None:
        self._capture(_payload(FIX_OK))
        health = self.svc.health()
        self.assertEqual(set(health.keys()), set(HEALTH_FIELDS))
        self.assertEqual(len(health), 8)
        self.assertFalse(health["scoring_touched"])
        self.assertNotIn("props", health)
        self.assertNotIn("cookie", health)
        self.assertNotIn("token", health)

    def test_every_route_scoring_untouched(self) -> None:
        self._capture(_payload(FIX_OK))
        self.assertFalse(self.svc.latest_snapshot()["scoring_touched"])
        self.assertFalse(self.svc.board_history()["scoring_touched"])
        self.assertFalse(self.svc.health()["scoring_touched"])

    def test_default_authoritative_false(self) -> None:
        body = {
            "source": "prizepicks_browser_bridge",
            "captured_at": "2026-07-24T04:00:00Z",
            "payload": _payload(FIX_OK),
        }
        result = self.svc.capture_board(body)
        self.assertFalse(result.authoritative_capture)
        self.assertEqual(result.cleared_status, "NOT_CLEARED")

    def test_http_paths_locked_and_token(self) -> None:
        from http.client import HTTPConnection
        from threading import Thread

        handler = create_handler(self.svc)
        from http.server import ThreadingHTTPServer

        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            conn = HTTPConnection("127.0.0.1", port, timeout=5)
            conn.request("GET", PATH_HEALTH)
            resp = conn.getresponse()
            health = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(resp.status, 200)
            self.assertEqual(set(health.keys()), set(HEALTH_FIELDS))

            body = json.dumps(
                {
                    "source": "prizepicks_browser_bridge",
                    "captured_at": "2026-07-24T05:00:00Z",
                    "authoritative_capture": False,
                    "payload": _payload(FIX_OK),
                }
            ).encode("utf-8")
            conn.request(
                "POST",
                PATH_CAPTURE,
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "X-MBM-Bridge-Token": "test-token",
                    "Content-Length": str(len(body)),
                },
            )
            cap = conn.getresponse()
            cap_body = json.loads(cap.read().decode("utf-8"))
            self.assertEqual(cap.status, 200)
            self.assertEqual(cap_body["status"], "CAPTURED")
            self.assertEqual(cap_body["cleared_status"], "NOT_CLEARED")
            self.assertFalse(cap_body["scoring_touched"])

            conn.request("GET", PATH_LATEST)
            latest = json.loads(conn.getresponse().read().decode("utf-8"))
            self.assertFalse(latest["scoring_touched"])

            conn.request("GET", PATH_HISTORY)
            history = json.loads(conn.getresponse().read().decode("utf-8"))
            self.assertFalse(history["scoring_touched"])
            self.assertGreaterEqual(history["count"], 1)
            conn.close()
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
