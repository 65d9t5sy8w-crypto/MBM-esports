"""Headshots opportunity/conversion gates (fixture-only, no live APIs)."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from mbm.behavioral.adapters.cs2.projection import project_headshots_from_envelope
from mbm.intake.normalization import normalize_manual_panel
from mbm.intake.types import Recommendation

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "cs2"
NOW = datetime(2026, 7, 23, 20, 0, 0, tzinfo=timezone.utc)


def _decide(name: str):
    payload = json.loads((FIXTURES / name / "normalized.json").read_text(encoding="utf-8"))
    env = normalize_manual_panel(payload)
    return project_headshots_from_envelope(env, now=NOW)


class TestCs2HeadshotsGates(unittest.TestCase):
    def test_eligible_can_recommend_over_under_or_pass(self) -> None:
        decision = _decide("eligible_headshots")
        self.assertIn(decision.action, {Recommendation.OVER, Recommendation.UNDER, Recommendation.PASS})
        self.assertNotEqual(decision.action.value, "WATCHLIST")
        self.assertTrue(decision.distribution_valid)
        self.assertAlmostEqual(sum(decision.probabilities.values()), 1.0, places=9)
        self.assertTrue(decision.provenance)
        self.assertTrue(decision.opportunity.passed)
        self.assertTrue(decision.conversion.passed)
        # Constructed fixture has mean HS above line → OVER
        self.assertIs(decision.action, Recommendation.OVER)

    def test_unresolved_identity_is_pass(self) -> None:
        decision = _decide("unresolved_identity")
        self.assertIs(decision.action, Recommendation.PASS)
        self.assertIn("identity", decision.reasons[0].lower())

    def test_stale_evidence_is_pass(self) -> None:
        decision = _decide("stale_evidence")
        self.assertIs(decision.action, Recommendation.PASS)
        self.assertIn("stale", decision.reasons[0].lower())

    def test_missing_scope_is_pass(self) -> None:
        decision = _decide("missing_scope")
        self.assertIs(decision.action, Recommendation.PASS)

    def test_opportunity_gate_failure_is_pass(self) -> None:
        decision = _decide("opportunity_fail")
        self.assertIs(decision.action, Recommendation.PASS)
        self.assertIn("opportunity", decision.reasons[0].lower())
        self.assertFalse(decision.opportunity.passed)

    def test_conversion_gate_failure_is_pass(self) -> None:
        decision = _decide("conversion_fail")
        self.assertIs(decision.action, Recommendation.PASS)
        self.assertIn("conversion", decision.reasons[0].lower())
        self.assertFalse(decision.conversion.passed)

    def test_no_generic_data_unavailable(self) -> None:
        for name in (
            "unresolved_identity",
            "stale_evidence",
            "missing_scope",
            "opportunity_fail",
            "conversion_fail",
        ):
            decision = _decide(name)
            joined = " ".join(decision.reasons).lower()
            self.assertNotIn("data unavailable", joined)


if __name__ == "__main__":
    unittest.main()
