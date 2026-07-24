"""OddsPapi adapter tests — synthetic fixtures only (not live provider evidence)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mbm.analyst.cs2_bridge import decide_headshots
from mbm.core_pin import core_ready
from mbm.providers.oddspapi.client import (
    API_KEY_ENV,
    OddsPapiClient,
    OddsPapiHttpResult,
    USER_AGENT,
    redact_api_key,
)
from mbm.providers.oddspapi.pipeline import refresh_from_synthetic
from mbm.intake.types import Recommendation

ROOT = Path(__file__).resolve().parents[1]
SYN_OK = ROOT / "fixtures" / "oddspapi" / "synthetic" / "ok"
SYN_UNAVAIL = ROOT / "fixtures" / "oddspapi" / "synthetic" / "unavailable"


class TestOddsPapiSyntheticFixtures(unittest.TestCase):
    def test_synthetic_ok_is_labeled_not_oddspapi_evidence(self) -> None:
        env = refresh_from_synthetic(SYN_OK, target_player_id="9001", line=18.5)
        self.assertEqual(env.source, "synthetic_test_fixture")
        self.assertTrue(env.map_context.get("not_for_projection"))
        self.assertEqual(env.fixture.team_a, "Test Team Alpha")
        self.assertEqual(env.fixture.team_b, "Test Team Bravo")
        self.assertTrue(env.market_lines)
        self.assertEqual(env.market_lines[0].stat, "headshots")
        self.assertEqual(env.market_lines[0].line, 18.5)
        captured = next(p.value for p in env.provenance if p.name == "captured_at")
        self.assertIsNone(captured)

    def test_synthetic_extracts_headshots_line_from_odds(self) -> None:
        env = refresh_from_synthetic(SYN_OK)
        self.assertTrue(any(m.stat == "headshots" and m.line == 18.5 for m in env.market_lines))
        self.assertEqual(env.target_player_id, "9001")

    def test_synthetic_unavailable_becomes_explicit_pass_reason(self) -> None:
        env = refresh_from_synthetic(SYN_UNAVAIL)
        self.assertEqual(env.source, "synthetic_test_fixture")
        self.assertTrue(any(a.outcome == "unavailable" for a in env.source_attempts))
        decision = decide_headshots(env)
        self.assertIs(decision.action, Recommendation.PASS)
        joined = " ".join(decision.reasons).lower()
        self.assertIn("401", joined)
        self.assertNotIn("data unavailable", joined)

    def test_fixture_meta_required(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp)
            (bad / "fixtures.json").write_text(
                json.dumps({"results": [{"fixtureId": "x", "participants": {}}]}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                refresh_from_synthetic(bad)

    def test_user_agent_is_honest_mbm(self) -> None:
        self.assertTrue(USER_AGENT.startswith("MBM-esports/"))
        self.assertNotIn("Chrome", USER_AGENT)
        self.assertNotIn("sec-ch-ua", USER_AGENT.lower())

    def test_client_headers_have_no_browser_impersonation(self) -> None:
        client = OddsPapiClient(api_key="test-key")
        headers = client._headers()
        self.assertEqual(set(headers), {"Accept", "User-Agent"})
        self.assertEqual(headers["User-Agent"], USER_AGENT)
        for banned in ("Origin", "Referer", "sec-ch-ua", "sec-fetch-mode"):
            self.assertNotIn(banned, headers)

    def test_redact_api_key_from_urls(self) -> None:
        raw = "https://v5.oddspapi.io/en/fixtures?sportId=17&apiKey=secret-value"
        self.assertIn("apiKey=REDACTED", redact_api_key(raw))
        self.assertNotIn("secret-value", redact_api_key(raw))

    def test_missing_api_key_is_explicit_unavailable(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            # Force empty key even if env is set in the shell.
            client = OddsPapiClient(api_key="")
            result = client.fixtures()
        self.assertFalse(result.available)
        self.assertIn(API_KEY_ENV, result.unavailable_reason or "")
        self.assertIn("apiKey", result.unavailable_reason or "")

    def test_live_unavailable_no_retry(self) -> None:
        client = OddsPapiClient(api_key="test-key")
        fake = OddsPapiHttpResult(
            ok=False,
            status=401,
            content_type="application/json",
            body=b'{"error":401}',
            url="https://v5.oddspapi.io/en/fixtures?apiKey=REDACTED",
            json_body=None,
            unavailable_reason="OddsPapi unavailable: HTTP 401 content_type=application/json",
        )
        with patch.object(client, "request", return_value=fake) as req:
            result = client.fixtures()
            self.assertEqual(req.call_count, 1)
        self.assertFalse(result.available)
        self.assertIn("401", result.unavailable_reason or "")

    def test_core_still_blocked_after_synthetic_refresh(self) -> None:
        refresh_from_synthetic(SYN_OK, target_player_id="9001", line=18.5)
        self.assertFalse(core_ready())


if __name__ == "__main__":
    unittest.main()
