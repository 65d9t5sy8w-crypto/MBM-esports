"""NBA analysis gates + dashboard assembly (synthetic only)."""

from __future__ import annotations

import ast
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from mbm.analyst.nba_bridge import decide_nba_prop
from mbm.behavioral.adapters.nba.gates import evaluate_nba_prop, one_selection_per_game
from mbm.behavioral.adapters.nba.leakage import PointInTimeCutoff
from mbm.behavioral.adapters.nba.types import NbaRecommendation
from mbm.dashboard.nba import assemble_nba_snapshot, render_nba_board
from mbm.providers.balldontlie.pipeline import refresh_from_synthetic

ROOT = Path(__file__).resolve().parents[1]
SYN_OK = ROOT / "fixtures" / "balldontlie" / "synthetic" / "ok"
DASHBOARD_DIR = ROOT / "mbm" / "dashboard"


class TestNbaAnalysis(unittest.TestCase):
    def test_evaluate_prop_with_cutoff_and_research(self) -> None:
        env = refresh_from_synthetic(SYN_OK, target_player_id="237", line=27.5)
        # Synthetic is not_for_projection → evidence gate fails → PASS
        decision = evaluate_nba_prop(
            env,
            cutoff=PointInTimeCutoff(
                game_id="910001",
                game_start="2025-11-15T02:00:00Z",
                as_of="2025-11-15T02:00:00Z",
                recorded_at="2025-11-15T01:00:00Z",
            ),
        )
        self.assertEqual(decision.action, NbaRecommendation.PASS)
        self.assertIn("not_for_projection", decision.evidence_gate.detail)
        self.assertGreaterEqual(decision.prop.sample_size, 5)

    def test_one_selection_per_game(self) -> None:
        env = refresh_from_synthetic(SYN_OK, target_player_id="237", line=27.5)
        # Force two decisions by evaluating twice; both PASS for synthetic.
        d1 = evaluate_nba_prop(env)
        d2 = evaluate_nba_prop(env)
        selected = one_selection_per_game([d1, d2])
        self.assertEqual(len(selected), 1)

    def test_bridge_maps_more_less(self) -> None:
        env = refresh_from_synthetic(SYN_OK, target_player_id="237", line=27.5)
        # Mark as projection-eligible for bridge path by cloning context
        payload = env.to_dict()
        payload["map_context"]["not_for_projection"] = False
        payload["source"] = "balldontlie"
        payload["evidence_status"] = "verified"
        from mbm.intake.types import EvidenceEnvelope, EvidenceStatus, IdentityStatus

        live_like = EvidenceEnvelope.from_dict(payload)
        # from_dict may not flip status enums from nested edits — set explicitly
        live_like.evidence_status = EvidenceStatus.VERIFIED
        live_like.identity_status = IdentityStatus.RESOLVED
        live_like.map_context["not_for_projection"] = False
        decision = decide_nba_prop(
            live_like,
            cutoff=PointInTimeCutoff(
                game_id="910001",
                game_start="2025-11-15T02:00:00Z",
                as_of="2025-11-15T02:00:00Z",
                recorded_at="2025-11-15T01:00:00Z",
            ),
        )
        self.assertIn(decision.map_context.get("nba_action"), {"MORE", "LESS", "PASS"})
        self.assertIn("point_in_time_cutoff", decision.map_context)
        self.assertIn("evaluated_market", decision.map_context)

    def test_board_uses_evaluated_market_not_first_line(self) -> None:
        from mbm.analyst.decision import CanonicalDecision
        from mbm.analyst.models import GateView
        from mbm.intake.types import (
            EvidenceEnvelope,
            EvidenceStatus,
            FixtureIdentity,
            IdentityStatus,
            MarketLine,
            MarketScope,
            Recommendation,
        )

        env = EvidenceEnvelope(
            source="synthetic_test_fixture",
            captured_at="2025-11-15T01:00:00Z",
            fixture=FixtureIdentity(
                event_id="synthetic-910001",
                team_a="A",
                team_b="B",
                start_time="2025-11-15T02:00:00Z",
                format="nba_game",
                market_scope=MarketScope.FULL_GAME,
            ),
            players=[],
            match_logs=[],
            map_context={},
            market_lines=[
                MarketLine("1", "rebounds", 10.5, MarketScope.FULL_GAME),
                MarketLine("237", "points", 27.5, MarketScope.FULL_GAME),
            ],
            evidence_status=EvidenceStatus.INCOMPLETE,
            identity_status=IdentityStatus.UNRESOLVED,
            target_player_id="237",
        )

        def decide(_envelope: EvidenceEnvelope) -> CanonicalDecision:
            return CanonicalDecision(
                action=Recommendation.PASS,
                reasons=("demo",),
                opportunity=GateView("research", False, "demo", None),
                conversion=GateView("a_tier_certification", False, "pending", None),
                probabilities={"PASS": 1.0, "OVER": 0.0, "UNDER": 0.0},
                provenance=(),
                evidence_status="incomplete",
                identity_status="unresolved",
                identity_notes=(),
                raw_refs=(),
                map_context={
                    "nba_action": "PASS",
                    "nba_grade": "PASS",
                    "evaluated_market": {
                        "player_id": "237",
                        "stat": "points",
                        "line": 27.5,
                    },
                },
                actionable=False,
            )

        snap = assemble_nba_snapshot(
            [("nba-demo", env)],
            decide,
            data_label="nba-synthetic/demo",
            now=datetime(2025, 11, 15, 1, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(snap.board[0].player_id, "237")
        self.assertEqual(snap.board[0].stat, "points")
        self.assertEqual(snap.board[0].line, 27.5)


class TestNbaDashboard(unittest.TestCase):
    def test_api_nba_snapshot_route_configured(self) -> None:
        from mbm.dashboard.app import create_handler
        from mbm.analyst.models import CalibrationView, DashboardSnapshot

        empty_cal = CalibrationView(0, 0, [], [], ())
        cs2 = DashboardSnapshot(
            "cs2", "demo", "blocked", False, "2025-01-01T00:00:00Z", [], {}, [], empty_cal
        )
        nba = DashboardSnapshot(
            "nba", "demo", "blocked", False, "2025-01-01T00:00:00Z", [], {}, [], empty_cal
        )
        handler_cls = create_handler(cs2, nba_snapshot=nba)
        self.assertIsNotNone(handler_cls.nba_snapshot_provider)

    def test_assemble_and_render(self) -> None:
        env = refresh_from_synthetic(SYN_OK, target_player_id="237", line=27.5)
        demo = ROOT / "fixtures" / "nba" / "demo_prop"
        demo.mkdir(parents=True, exist_ok=True)
        (demo / "normalized.json").write_text(
            json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        snap = assemble_nba_snapshot(
            [("nba-demo-910001", env)],
            decide_nba_prop,
            data_label="nba-synthetic/demo",
            now=datetime(2025, 11, 15, 1, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(len(snap.board), 1)
        html = render_nba_board(snap)
        self.assertIn("MBM NBA Research Board", html)
        self.assertIn("Certification pending", html)

    def test_dashboard_package_avoids_balldontlie_http_client(self) -> None:
        for path in DASHBOARD_DIR.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn("providers.balldontlie.client", node.module)


if __name__ == "__main__":
    unittest.main()
