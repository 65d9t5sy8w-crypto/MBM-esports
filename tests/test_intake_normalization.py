"""Normalization + secret scrubbing (fixture-only)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from mbm.intake.normalization import normalize_manual_panel, strip_secrets
from mbm.intake.raw import RawStore

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "cs2"


class TestIntakeNormalization(unittest.TestCase):
    def test_normalize_eligible_fixture(self) -> None:
        payload = json.loads(
            (FIXTURES / "eligible_headshots" / "normalized.json").read_text(encoding="utf-8")
        )
        env = normalize_manual_panel(payload, raw_ref="fixtures/cs2/eligible_headshots/raw/payload.json")
        self.assertEqual(env.fixture.event_id, "mbm-cs2-fixture-eligible-001")
        self.assertEqual(env.fixture.market_scope.value, "maps_1_2")
        self.assertEqual(len(env.match_logs), 10)
        self.assertEqual(env.market_lines[0].stat, "headshots")
        self.assertIsNotNone(env.raw_ref)

    def test_strip_secrets_never_persist(self) -> None:
        dirty = {
            "source": "manual",
            "Authorization": "Bearer SECRET",
            "cookie": "session=abc",
            "api_key": "RGAPI-should-not-appear",
            "nested": {"token": "x", "ok": 1},
            "captured_at": "2026-07-23T18:00:00Z",
            "fixture": {
                "event_id": "e1",
                "team_a": "A",
                "team_b": "B",
                "start_time": "2026-07-24T16:00:00Z",
                "format": "bo3",
                "market_scope": "maps_1_2",
            },
            "players": [],
            "match_logs": [],
            "map_context": {},
            "market_lines": [],
            "evidence_status": "incomplete",
        }
        cleaned = strip_secrets(dirty)
        blob = json.dumps(cleaned)
        self.assertNotIn("Authorization", cleaned)
        self.assertNotIn("cookie", cleaned)
        self.assertNotIn("api_key", cleaned)
        self.assertNotIn("token", cleaned["nested"])
        self.assertNotIn("RGAPI", blob)
        self.assertEqual(cleaned["nested"]["ok"], 1)

    def test_raw_store_immutable(self) -> None:
        store = RawStore(FIXTURES)
        event_id = "mbm-cs2-raw-immutability"
        first = {"hello": 1}
        store.write(event_id, first, filename="imm.json")
        with self.assertRaises(ValueError):
            store.write(event_id, {"hello": 2}, filename="imm.json")
        # cleanup written temp raw
        path = FIXTURES / event_id / "raw" / "imm.json"
        path.unlink(missing_ok=True)
        (FIXTURES / event_id / "raw").rmdir()
        (FIXTURES / event_id).rmdir()


if __name__ == "__main__":
    unittest.main()
