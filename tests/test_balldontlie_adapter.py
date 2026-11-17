"""BallDontLie NBA adapter certification — synthetic fixtures + disabled paid paths."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from unittest.mock import patch

from mbm.providers.balldontlie.client import (
    API_KEY_ENV,
    ENABLED_PATHS,
    BallDontLieHttpResult,
    BallDontLieNbaAdapter,
    redact_secrets,
    redact_url,
)
from mbm.providers.balldontlie.endpoints import DISABLED_PATHS, AccessTier, get_endpoint
from mbm.providers.balldontlie.pipeline import refresh_from_synthetic

ROOT = Path(__file__).resolve().parents[1]
SYN_OK = ROOT / "fixtures" / "balldontlie" / "synthetic" / "ok"
SYN_UNAVAIL = ROOT / "fixtures" / "balldontlie" / "synthetic" / "unavailable"
PROVIDER_ROOT = ROOT / "mbm" / "providers" / "balldontlie"


class TestBallDontLieAdapter(unittest.TestCase):
    def test_synthetic_ok_not_labeled_as_live_evidence(self) -> None:
        env = refresh_from_synthetic(SYN_OK, target_player_id="237", line=27.5)
        self.assertEqual(env.source, "synthetic_test_fixture")
        self.assertTrue(env.map_context.get("not_for_projection"))
        self.assertEqual(env.fixture.team_a, "Los Angeles Lakers")
        self.assertEqual(env.fixture.team_b, "LA Clippers")
        self.assertTrue(any(m.stat == "points" and m.line == 27.5 for m in env.market_lines))
        captured = next(p.value for p in env.provenance if p.name == "captured_at")
        self.assertIsNone(captured)
        self.assertGreaterEqual(len(env.map_context.get("sportsbook_prices") or []), 1)

    def test_unavailable_odds_fixture_records_reason(self) -> None:
        env = refresh_from_synthetic(SYN_UNAVAIL)
        self.assertTrue(
            any("401" in a.detail or "unavailable" in a.outcome for a in env.source_attempts)
        )

    def test_enabled_paths_are_free_only(self) -> None:
        for path in ENABLED_PATHS:
            spec = get_endpoint(path)
            self.assertIsNotNone(spec)
            assert spec is not None
            self.assertEqual(spec.tier, AccessTier.FREE)
            self.assertTrue(spec.enabled)

    def test_paid_endpoints_disabled_without_network(self) -> None:
        adapter = BallDontLieNbaAdapter(api_key="test-key-not-real")
        for method in ("stats", "player_injuries", "advanced_stats", "odds", "player_props", "lineups"):
            with patch("urllib.request.urlopen") as urlopen:
                result = getattr(adapter, method)()
                urlopen.assert_not_called()
            self.assertFalse(result.enabled)
            self.assertFalse(result.available)
            self.assertIn("disabled", (result.unavailable_reason or "").lower())

    def test_rejects_unknown_path(self) -> None:
        adapter = BallDontLieNbaAdapter(api_key="test-key")
        with self.assertRaises(ValueError):
            adapter.request("/nba/v1/not_a_real_endpoint")

    def test_players_active_query_not_authorized_as_player_id(self) -> None:
        from mbm.providers.balldontlie.endpoints import canonicalize_path, is_enabled

        self.assertEqual(
            canonicalize_path("/nba/v1/players/active?per_page=1"),
            "/nba/v1/players/active",
        )
        self.assertFalse(is_enabled("/nba/v1/players/active?per_page=1"))
        adapter = BallDontLieNbaAdapter(api_key="test-key")
        with patch("urllib.request.urlopen") as urlopen:
            result = adapter.request("/nba/v1/players/active?per_page=1")
            urlopen.assert_not_called()
        self.assertFalse(result.enabled)
        self.assertIn("disabled", (result.unavailable_reason or "").lower())

    def test_redact_secrets_full_authorization_value(self) -> None:
        self.assertNotIn(
            "secret-token",
            redact_secrets('{"authorization":"Bearer secret-token"}'),
        )
        self.assertNotIn("secret-token", redact_secrets("Authorization: Bearer secret-token"))
        self.assertIn("REDACTED", redact_secrets("Authorization: secret-token"))

    def test_incomplete_read_returns_unavailable(self) -> None:
        import http.client

        adapter = BallDontLieNbaAdapter(api_key="test-key")
        with patch("urllib.request.urlopen", side_effect=http.client.IncompleteRead(b"partial")):
            result = adapter.teams()
        self.assertFalse(result.available)
        self.assertIn("transport error", result.unavailable_reason or "")

    def test_missing_key_unavailable(self) -> None:
        adapter = BallDontLieNbaAdapter(api_key="")
        result = adapter.teams()
        self.assertFalse(result.available)
        self.assertIn(API_KEY_ENV, result.unavailable_reason or "")

    def test_redact_secrets_and_urls(self) -> None:
        self.assertIn("REDACTED", redact_secrets("Authorization: super-secret-key"))
        self.assertIn("REDACTED", redact_url("https://api.balldontlie.io/nba/v1/games?apiKey=abc"))

    def test_free_helpers_authorized(self) -> None:
        adapter = BallDontLieNbaAdapter(api_key="test-key")
        with patch.object(adapter, "request") as req:
            req.return_value = BallDontLieHttpResult(
                ok=True,
                status=200,
                content_type="application/json",
                body=b'{"data":[]}',
                url="https://api.balldontlie.io/nba/v1/games",
                path="/nba/v1/games",
                json_body={"data": []},
                unavailable_reason=None,
                enabled=True,
            )
            adapter.games(per_page=1)
            self.assertEqual(req.call_args.args[0], "/nba/v1/games")

    def test_provider_code_has_no_hardcoded_api_keys(self) -> None:
        for path in PROVIDER_ROOT.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"Authorization:\s*[A-Za-z0-9_\-]{20,}")

    def test_disabled_paths_nonempty(self) -> None:
        self.assertIn("/nba/v2/odds", DISABLED_PATHS)
        self.assertIn("/nba/v2/stats/advanced", DISABLED_PATHS)
        self.assertIn("/nba/v1/player_injuries", DISABLED_PATHS)

    def test_oddspapi_untouched_by_balldontlie_imports(self) -> None:
        oddspapi = ROOT / "mbm" / "providers" / "oddspapi"
        for path in oddspapi.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn("balldontlie", node.module)


if __name__ == "__main__":
    unittest.main()
