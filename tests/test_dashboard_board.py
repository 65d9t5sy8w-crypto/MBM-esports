"""Analyst dashboard board assembly, PASS rendering, provenance visibility."""

from __future__ import annotations

import ast
import unittest
from datetime import datetime, timezone
from pathlib import Path

from mbm.analyst.assembly import build_dashboard_snapshot
from mbm.analyst.cs2_bridge import decide_headshots
from mbm.dashboard.render import render_board, render_pick
from mbm.intake.types import Recommendation

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "cs2"
NOW = datetime(2026, 7, 23, 20, 0, 0, tzinfo=timezone.utc)
DASHBOARD_DIR = ROOT / "mbm" / "dashboard"


def _snapshot():
    return build_dashboard_snapshot(
        FIXTURES,
        lambda env: decide_headshots(env, now=NOW),
        data_label="fixture/demo",
        now=NOW,
    )


class TestDashboardImports(unittest.TestCase):
    def test_dashboard_package_has_no_cs2_adapter_imports(self) -> None:
        for path in DASHBOARD_DIR.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertNotIn("adapters.cs2", alias.name)
                        self.assertFalse(alias.name.startswith("mbm.behavioral.adapters.cs2"))
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn("adapters.cs2", node.module)
                    self.assertFalse(node.module.startswith("mbm.behavioral.adapters.cs2"))


class TestBoardAssembly(unittest.TestCase):
    def test_board_includes_eligible_headshots_fixture(self) -> None:
        snap = _snapshot()
        self.assertTrue(snap.board)
        events = {row.event_id for row in snap.board}
        self.assertIn("mbm-cs2-fixture-eligible-001", events)
        eligible_rows = [r for r in snap.board if r.event_id == "mbm-cs2-fixture-eligible-001"]
        self.assertEqual(len(eligible_rows), 1)
        row = eligible_rows[0]
        self.assertEqual(row.stat, "headshots")
        self.assertEqual(row.market_scope, "maps_1_2")
        self.assertEqual(row.data_label, "fixture/demo")
        self.assertIn(row.recommendation, {"OVER", "UNDER", "PASS"})

    def test_core_blocked_means_not_eligible(self) -> None:
        snap = _snapshot()
        self.assertFalse(snap.core_ready)
        self.assertIn("BLOCKED", snap.core_status)
        for row in snap.board:
            self.assertFalse(row.eligible)
            self.assertIn("Core BLOCKED", row.eligibility_reason)

    def test_pass_rows_render_explicit_reason(self) -> None:
        snap = _snapshot()
        pass_picks = [p for p in snap.picks.values() if p.board.recommendation == Recommendation.PASS.value]
        self.assertTrue(pass_picks)
        for pick in pass_picks:
            self.assertIsNotNone(pick.pass_reason)
            self.assertTrue(str(pick.pass_reason).startswith("PASS") or "PASS" in str(pick.pass_reason))
            html = render_pick(snap, pick)
            self.assertIn("PASS reason", html)
            self.assertIn("fixture / demo data", html)

    def test_evidence_and_provenance_visible(self) -> None:
        snap = _snapshot()
        pick = next(p for p in snap.picks.values() if "eligible-001" in p.pick_id)
        self.assertTrue(pick.source_attempts)
        self.assertTrue(pick.provenance)
        self.assertTrue(pick.raw_refs)
        self.assertIn("map_pool", pick.map_context)
        html = render_pick(snap, pick)
        self.assertIn("Source-attempt ledger", html)
        self.assertIn("Feature provenance", html)
        self.assertIn("Raw evidence references", html)
        self.assertIn("Headshots gates", html)

    def test_board_html_shows_core_banner_and_fixture(self) -> None:
        snap = _snapshot()
        html = render_board(snap)
        self.assertIn("Core BLOCKED", html)
        self.assertIn("mbm-cs2-fixture-eligible-001", html)
        self.assertIn("Today", html)
        self.assertIn("fixture / demo data", html)

    def test_calibration_marks_insufficient_sample(self) -> None:
        snap = _snapshot()
        self.assertGreaterEqual(snap.calibration.projection_count, 1)
        for bucket in snap.calibration.by_market + snap.calibration.by_recommendation:
            self.assertEqual(bucket.sample_state, "insufficient_sample")


if __name__ == "__main__":
    unittest.main()
