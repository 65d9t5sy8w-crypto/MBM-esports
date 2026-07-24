"""OddsPapi v4 adapter certification — synthetic fixtures only."""

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
    AUTHORIZED_V4_PATHS,
    BASE_URL,
    SPORT_ID_CS2,
    SPORT_ID_LOL,
    SPORT_ID_VALORANT,
    USER_AGENT,
    VERIFIED_ESPORTS_SPORT_IDS,
    OddsPapiHttpResult,
    OddsPapiV4Adapter,
    redact_api_key,
)
from mbm.providers.oddspapi.normalize import (
    _select_fixture,
    _start_time_iso,
    normalize_oddspapi_bundle,
)
from mbm.providers.oddspapi.pipeline import _write_live_raw, refresh_from_synthetic
from mbm.intake.raw.store import RawStore
from mbm.intake.types import Recommendation

ROOT = Path(__file__).resolve().parents[1]
SYN_OK = ROOT / "fixtures" / "oddspapi" / "synthetic" / "ok"
SYN_UNAVAIL = ROOT / "fixtures" / "oddspapi" / "synthetic" / "unavailable"
PROD_ROOTS = (
    ROOT / "mbm" / "providers" / "oddspapi",
    ROOT / "scripts" / "refresh_oddspapi.py",
)


class TestOddsPapiV4Certification(unittest.TestCase):
    def test_synthetic_ok_is_labeled_not_oddspapi_evidence(self) -> None:
        env = refresh_from_synthetic(SYN_OK, sport_id=SPORT_ID_CS2)
        self.assertEqual(env.source, "synthetic_test_fixture")
        self.assertTrue(env.map_context.get("not_for_projection"))
        self.assertEqual(env.fixture.team_a, "Test Team Alpha")
        self.assertEqual(env.fixture.team_b, "Test Team Bravo")
        self.assertEqual(env.map_context.get("api_version"), "v4")
        self.assertEqual(env.map_context.get("sport_id"), SPORT_ID_CS2)
        self.assertGreaterEqual(len(env.map_context.get("pinnacle_prices") or []), 1)
        # Synthetic ok board is Pinnacle moneyline only — no verified headshot claim.
        self.assertEqual(env.map_context.get("player_prop_claim"), "none_verified_from_v4_payload")
        self.assertFalse(any(m.stat == "headshots" for m in env.market_lines))
        captured = next(p.value for p in env.provenance if p.name == "captured_at")
        self.assertIsNone(captured)

    def test_mason_attached_line_is_explicit_not_provider_prop_claim(self) -> None:
        env = refresh_from_synthetic(
            SYN_OK, target_player_id="9001", line=18.5, sport_id=SPORT_ID_CS2
        )
        self.assertTrue(any(m.stat == "headshots" and m.line == 18.5 for m in env.market_lines))
        self.assertEqual(env.map_context.get("player_prop_claim"), "none_verified_from_v4_payload")

    def test_verified_sport_ids_preserved(self) -> None:
        self.assertEqual(VERIFIED_ESPORTS_SPORT_IDS, frozenset({17, 18, 61}))
        self.assertEqual(SPORT_ID_CS2, 17)
        self.assertEqual(SPORT_ID_LOL, 18)
        self.assertEqual(SPORT_ID_VALORANT, 61)

    def test_adapter_not_cs2_only(self) -> None:
        adapter = OddsPapiV4Adapter(api_key="test-key")
        for sport_id in (SPORT_ID_CS2, SPORT_ID_LOL, SPORT_ID_VALORANT):
            with patch.object(adapter, "request") as req:
                req.return_value = OddsPapiHttpResult(
                    ok=True,
                    status=200,
                    content_type="application/json",
                    body=b"[]",
                    url=f"{BASE_URL}/v4/tournaments",
                    json_body=[],
                    unavailable_reason=None,
                )
                adapter.tournaments(sport_id=sport_id)
                path = req.call_args.args[0]
                params = req.call_args.args[1]
                self.assertEqual(path, "/v4/tournaments")
                self.assertEqual(params["sportId"], sport_id)

    def test_rejects_unverified_sport_id(self) -> None:
        adapter = OddsPapiV4Adapter(api_key="test-key")
        with self.assertRaises(ValueError):
            adapter.tournaments(sport_id=10)

    def test_rejects_non_v4_paths(self) -> None:
        adapter = OddsPapiV4Adapter(api_key="test-key")
        with self.assertRaises(ValueError):
            adapter.request("/v5/sports")
        with self.assertRaises(ValueError):
            adapter.request("/sports")
        with self.assertRaises(ValueError):
            adapter.request("/v4/players")
        self.assertEqual(
            AUTHORIZED_V4_PATHS,
            frozenset({"/v4/sports", "/v4/tournaments", "/v4/odds-by-tournaments"}),
        )

    def test_timeout_returns_unavailable_not_crash(self) -> None:
        adapter = OddsPapiV4Adapter(api_key="test-key")
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            result = adapter.sports()
        self.assertFalse(result.available)
        self.assertIn("transport error", result.unavailable_reason or "")
        self.assertIn("timed out", result.unavailable_reason or "")

    def test_start_time_iso_parses_serialized_epochs(self) -> None:
        fallback = "1970-01-01T00:00:00Z"
        self.assertTrue(_start_time_iso("1785002400", fallback).startswith("2026-"))
        self.assertTrue(_start_time_iso("1785002400.0", fallback).startswith("2026-"))
        self.assertTrue(_start_time_iso("+1785002400", fallback).startswith("2026-"))
        self.assertEqual(_start_time_iso("not-a-time", fallback), fallback)
        self.assertEqual(
            _start_time_iso("2026-07-25T18:00:00.000Z", fallback),
            "2026-07-25T18:00:00.000Z",
        )

    def test_select_fixture_prefers_has_odds_with_pinnacle(self) -> None:
        bare = {"fixtureId": "a", "hasOdds": False}
        odds_only = {"fixtureId": "b", "hasOdds": True, "bookmakerOdds": {}}
        priced = {
            "fixtureId": "c",
            "hasOdds": True,
            "bookmakerOdds": {
                "pinnacle": {
                    "markets": {
                        "1": {"outcomes": {"1": {"players": {"0": {"price": 1.9}}}}}
                    }
                }
            },
        }
        chosen, detail = _select_fixture([bare, odds_only, priced])
        self.assertEqual(chosen["fixtureId"], "c")
        self.assertIn("pinnacle", detail)

    def test_write_live_raw_preserves_original_body_bytes(self) -> None:
        raw_bytes = b'{"fixtureId":"x","keepOrder":true}'
        result = OddsPapiHttpResult(
            ok=True,
            status=200,
            content_type="application/json",
            body=raw_bytes,
            url="https://api.oddspapi.io/v4/sports?apiKey=REDACTED",
            json_body={"fixtureId": "x", "keepOrder": True},
            unavailable_reason=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            store = RawStore(Path(tmp))
            path = _write_live_raw(store, "evt1", "sports", result)
            written = Path(path).read_bytes()
            self.assertEqual(written, raw_bytes)
            meta = json.loads((Path(tmp) / "evt1" / "raw" / "sports.meta.json").read_text())
            self.assertEqual(meta["body_byte_length"], len(raw_bytes))
            self.assertNotIn("apiKey=secret", json.dumps(meta))

    def test_production_endpoints_are_v4_only(self) -> None:
        adapter = OddsPapiV4Adapter(api_key="test-key")
        captured: list[str] = []

        def _capture(path: str, params=None):
            captured.append(path)
            return OddsPapiHttpResult(
                ok=True,
                status=200,
                content_type="application/json",
                body=b"[]",
                url=f"{BASE_URL}{path}",
                json_body=[],
                unavailable_reason=None,
            )

        with patch.object(adapter, "request", side_effect=_capture):
            adapter.sports()
            adapter.tournaments(sport_id=SPORT_ID_LOL)
            adapter.odds_by_tournaments([17001], bookmaker="pinnacle")
        self.assertEqual(
            captured,
            ["/v4/sports", "/v4/tournaments", "/v4/odds-by-tournaments"],
        )

    def test_base_url_is_api_oddspapi_v4_host(self) -> None:
        self.assertEqual(BASE_URL, "https://api.oddspapi.io")
        self.assertNotIn("v5", BASE_URL)

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
            (bad / "odds_by_tournaments.json").write_text(
                json.dumps({"results": [{"fixtureId": "x"}]}),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                refresh_from_synthetic(bad)

    def test_user_agent_is_honest_mbm(self) -> None:
        self.assertTrue(USER_AGENT.startswith("MBM-esports/"))
        self.assertNotIn("Chrome", USER_AGENT)

    def test_client_headers_have_no_browser_impersonation(self) -> None:
        adapter = OddsPapiV4Adapter(api_key="test-key")
        headers = adapter._headers()
        self.assertEqual(set(headers), {"Accept", "User-Agent"})
        for banned in ("Origin", "Referer", "sec-ch-ua", "sec-fetch-mode"):
            self.assertNotIn(banned, headers)

    def test_redact_api_key_from_urls(self) -> None:
        raw = "https://api.oddspapi.io/v4/sports?apiKey=secret-value"
        self.assertIn("apiKey=REDACTED", redact_api_key(raw))
        self.assertNotIn("secret-value", redact_api_key(raw))

    def test_missing_api_key_is_explicit_unavailable(self) -> None:
        adapter = OddsPapiV4Adapter(api_key="")
        result = adapter.sports()
        self.assertFalse(result.available)
        self.assertIn(API_KEY_ENV, result.unavailable_reason or "")

    def test_live_unavailable_no_retry(self) -> None:
        adapter = OddsPapiV4Adapter(api_key="test-key")
        fake = OddsPapiHttpResult(
            ok=False,
            status=401,
            content_type="application/json",
            body=b'{"error":401}',
            url="https://api.oddspapi.io/v4/tournaments?apiKey=REDACTED",
            json_body=None,
            unavailable_reason="OddsPapi unavailable: HTTP 401 content_type=application/json",
        )
        with patch.object(adapter, "request", return_value=fake) as req:
            result = adapter.tournaments(sport_id=SPORT_ID_CS2)
            self.assertEqual(req.call_count, 1)
        self.assertFalse(result.available)
        self.assertIn("401", result.unavailable_reason or "")

    def test_zero_v5_in_production_code(self) -> None:
        offenders: list[str] = []
        for root in PROD_ROOTS:
            paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
            for path in paths:
                text = path.read_text(encoding="utf-8")
                if "v5" in text.lower():
                    offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(
            offenders,
            [],
            f"production code must contain zero 'v5' occurrences; found in {offenders}",
        )

    def test_core_still_blocked_after_synthetic_refresh(self) -> None:
        refresh_from_synthetic(SYN_OK, sport_id=SPORT_ID_CS2)
        self.assertFalse(core_ready())


if __name__ == "__main__":
    unittest.main()
