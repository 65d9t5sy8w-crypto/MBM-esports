"""BO3 adapter tests — synthetic fixtures only (not live provider evidence)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mbm.analyst.cs2_bridge import decide_headshots
from mbm.core_pin import core_ready
from mbm.providers.bo3gg.client import Bo3Client, Bo3HttpResult, USER_AGENT
from mbm.providers.bo3gg.pipeline import refresh_from_synthetic
from mbm.intake.types import Recommendation

ROOT = Path(__file__).resolve().parents[1]
SYN_OK = ROOT / "fixtures" / "bo3gg" / "synthetic" / "ok"
SYN_UNAVAIL = ROOT / "fixtures" / "bo3gg" / "synthetic" / "unavailable"


class TestBo3SyntheticFixtures(unittest.TestCase):
    def test_synthetic_ok_is_labeled_not_bo3_evidence(self) -> None:
        env = refresh_from_synthetic(SYN_OK, target_player_id="p1", line=18.5)
        self.assertEqual(env.source, "synthetic_test_fixture")
        self.assertTrue(env.map_context.get("not_for_projection"))
        self.assertEqual(env.fixture.team_a, "Test Team Alpha")
        self.assertEqual(env.fixture.team_b, "Test Team Bravo")
        self.assertNotIn("Team Liquid", env.fixture.team_a)
        self.assertNotIn("FaZe", env.fixture.team_b)
        captured = next(p.value for p in env.provenance if p.name == "captured_at")
        self.assertIsNone(captured)

    def test_synthetic_unavailable_becomes_explicit_pass_reason(self) -> None:
        env = refresh_from_synthetic(SYN_UNAVAIL)
        self.assertEqual(env.source, "synthetic_test_fixture")
        self.assertTrue(any(a.outcome == "unavailable" for a in env.source_attempts))
        decision = decide_headshots(env)
        self.assertIs(decision.action, Recommendation.PASS)
        joined = " ".join(decision.reasons).lower()
        self.assertIn("403", joined)
        self.assertNotIn("data unavailable", joined)

    def test_fixture_meta_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp)
            (bad / "upcoming.json").write_text(
                json.dumps({"results": [{"id": 1, "teams": []}]}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                refresh_from_synthetic(bad)

    def test_user_agent_is_honest_mbm(self) -> None:
        self.assertTrue(USER_AGENT.startswith("MBM-esports/"))
        self.assertNotIn("Chrome", USER_AGENT)
        self.assertNotIn("sec-ch-ua", USER_AGENT.lower())

    def test_client_headers_have_no_browser_impersonation(self) -> None:
        client = Bo3Client()
        headers = client._headers()
        self.assertEqual(set(headers), {"Accept", "User-Agent"})
        self.assertEqual(headers["User-Agent"], USER_AGENT)
        for banned in ("Origin", "Referer", "sec-ch-ua", "sec-fetch-mode"):
            self.assertNotIn(banned, headers)

    def test_live_unavailable_no_retry(self) -> None:
        client = Bo3Client()
        fake = Bo3HttpResult(
            ok=False,
            status=403,
            content_type="text/html",
            body=b"<html>",
            url="https://api.bo3.gg/api/v1/matches",
            json_body=None,
            unavailable_reason="BO3 unavailable: HTTP 403 content_type=text/html",
        )
        with patch.object(client, "request", return_value=fake) as req:
            result = client.upcoming_matches()
            self.assertEqual(req.call_count, 1)
        self.assertFalse(result.available)
        self.assertIn("403", result.unavailable_reason or "")

    def test_core_still_blocked_after_synthetic_refresh(self) -> None:
        refresh_from_synthetic(SYN_OK, target_player_id="p1", line=18.5)
        self.assertFalse(core_ready())


if __name__ == "__main__":
    unittest.main()
