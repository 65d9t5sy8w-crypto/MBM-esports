"""Evidence ledger / staleness / completeness (fixture-only)."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

from mbm.intake.evidence import assess_evidence, explicit_pass_message
from mbm.intake.identity import resolve_identity
from mbm.intake.normalization import normalize_manual_panel
from mbm.intake.types import EvidenceStatus, Recommendation

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "cs2"
NOW = datetime(2026, 7, 23, 20, 0, 0, tzinfo=timezone.utc)


def _load(name: str):
    payload = json.loads((FIXTURES / name / "normalized.json").read_text(encoding="utf-8"))
    return resolve_identity(normalize_manual_panel(payload))


class TestIntakeEvidence(unittest.TestCase):
    def test_eligible_actionable(self) -> None:
        assessment = assess_evidence(_load("eligible_headshots"), now=NOW)
        self.assertTrue(assessment.actionable)
        self.assertEqual(assessment.reasons, ())

    def test_stale_evidence_pass_reason(self) -> None:
        assessment = assess_evidence(_load("stale_evidence"), now=NOW)
        self.assertFalse(assessment.actionable)
        self.assertIs(assessment.recommendation_if_blocked, Recommendation.PASS)
        self.assertTrue(any("stale" in r for r in assessment.reasons))
        self.assertIs(assessment.envelope.evidence_status, EvidenceStatus.STALE)
        msg = explicit_pass_message(assessment.reasons, assessment.envelope.source_attempts)
        self.assertTrue(msg.startswith("PASS:"))
        self.assertNotIn("data unavailable", msg.lower())

    def test_missing_scope_not_blended(self) -> None:
        assessment = assess_evidence(_load("missing_scope"), now=NOW)
        self.assertFalse(assessment.actionable)
        joined = " ".join(assessment.reasons)
        self.assertTrue("scope" in joined or "incomplete" in joined)

    def test_unresolved_identity_blocked(self) -> None:
        assessment = assess_evidence(_load("unresolved_identity"), now=NOW)
        self.assertFalse(assessment.actionable)
        self.assertTrue(any("identity" in r for r in assessment.reasons))

    def test_source_attempts_recorded(self) -> None:
        assessment = assess_evidence(
            _load("stale_evidence"),
            now=NOW,
            approved_sources_attempted=["manual-fixture-drop", "hlthouse-export"],
        )
        sources = {a.source for a in assessment.envelope.source_attempts}
        self.assertIn("manual-fixture-drop", sources)
        self.assertIn("hlthouse-export", sources)


if __name__ == "__main__":
    unittest.main()
