"""CS2 vertical-slice tests.

Core-dependent assertions are skipped until the authentic wheel is vendored.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from mbm.behavioral.adapters.cs2.projection import (
    ALLOWED_ACTIONS,
    CORE_DISTRIBUTION_UNAVAILABLE,
    CORE_WHEEL,
    EXPECTED_CORE_SHA256,
    MISSING_PLAYER_LEVEL_CORE_INPUTS,
    CoreDependencyBlocked,
    core_ready,
    core_wheel_present,
    project_maps_1_2_headshots,
)
from mbm.behavioral.adapters.cs2.types import (
    CS2HeadshotsPanel,
    CS2MapWindow,
    CS2MarketKey,
)

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "cs2"
    / "eligible_headshots"
    / "panel.json"
)


class TestCs2Scaffold(unittest.TestCase):
    def test_eligible_fixture_loads(self) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        panel = CS2HeadshotsPanel.from_dict(payload)

        self.assertEqual(panel.match_id, "mbm-cs2-fixture-eligible-001")
        self.assertIs(panel.market, CS2MarketKey.MAPS_1_2_HEADSHOTS)
        self.assertEqual(panel.map_window, CS2MapWindow(1, 2))
        self.assertTrue(panel.approved_for_publication)
        self.assertIn("team_a_avg_hs_maps_1_2", panel.features)

    def test_allowed_actions_exclude_watchlist(self) -> None:
        self.assertEqual(ALLOWED_ACTIONS, frozenset({"OVER", "UNDER", "PASS"}))
        self.assertNotIn("WATCHLIST", ALLOWED_ACTIONS)

    def test_core_dependency_is_blocked_without_wheel(self) -> None:
        if core_wheel_present():
            self.skipTest(
                "authentic Core wheel is present; gate test applies only while blocked"
            )
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        panel = CS2HeadshotsPanel.from_dict(payload)
        with self.assertRaises(CoreDependencyBlocked):
            project_maps_1_2_headshots(panel)


@unittest.skipUnless(
    core_ready(),
    f"BLOCKED: Core not ready for acceptance (need {CORE_WHEEL} with "
    f"SHA-256 {EXPECTED_CORE_SHA256}). Skips do not count toward acceptance.",
)
class TestCs2VerticalSliceWithCore(unittest.TestCase):
    """Acceptance suite — runs only when authentic wheel is present and SHA matches.

    Skipped cases must never be reported as CS2 vertical-slice completion.
    """

    def setUp(self) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.panel = CS2HeadshotsPanel.from_dict(payload)

    def test_projection_result_not_none(self) -> None:
        result = project_maps_1_2_headshots(self.panel)
        self.assertIsNotNone(result)

    def test_no_fabricated_probability_distribution(self) -> None:
        """Core v0.1.0 has no calibrated action mass; probabilities stay empty."""
        result = project_maps_1_2_headshots(self.panel)
        self.assertEqual(result.probabilities, {})
        self.assertIn(
            result.decision.reason,
            {MISSING_PLAYER_LEVEL_CORE_INPUTS, CORE_DISTRIBUTION_UNAVAILABLE},
        )

    def test_complete_feature_provenance(self) -> None:
        result = project_maps_1_2_headshots(self.panel)
        provenance = result.provenance
        self.assertTrue(provenance)
        names = {item.name for item in provenance}
        for key in self.panel.features:
            self.assertIn(key, names)

    def test_publication_decision_fail_closed_without_core_distribution(self) -> None:
        result = project_maps_1_2_headshots(self.panel)
        decision = result.decision
        self.assertFalse(decision.eligible)
        self.assertEqual(decision.action, "PASS")
        self.assertNotEqual(decision.action, "WATCHLIST")
        # Fixture supplies team averages only — not player-level Core inputs.
        self.assertEqual(decision.reason, MISSING_PLAYER_LEVEL_CORE_INPUTS)
        names = {item.name for item in result.provenance}
        self.assertIn("missing_player_level_core_inputs", names)
        self.assertIn("refused_team_average_as_kill_share", names)

    def test_player_inputs_still_fail_closed_without_core_distribution(self) -> None:
        payload = {
            "match_id": self.panel.match_id,
            "market": self.panel.market.value,
            "map_window": {
                "start_map": self.panel.map_window.start_map,
                "end_map": self.panel.map_window.end_map,
            },
            "line": self.panel.line,
            "approved_for_publication": True,
            "features": {
                **self.panel.features,
                "kill_share": 0.55,
                "stability": 85.0,
                "eco_dependency": 0.05,
            },
        }
        panel = CS2HeadshotsPanel.from_dict(payload)
        result = project_maps_1_2_headshots(panel)
        self.assertEqual(result.probabilities, {})
        self.assertFalse(result.decision.eligible)
        self.assertEqual(result.decision.reason, CORE_DISTRIBUTION_UNAVAILABLE)
        self.assertTrue(result.scores)
        self.assertTrue(result.core_label)


if __name__ == "__main__":
    unittest.main()
