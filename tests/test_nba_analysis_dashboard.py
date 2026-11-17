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


class TestNbaDashboard(unittest.TestCase):
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
