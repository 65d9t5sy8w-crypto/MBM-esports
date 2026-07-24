"""Identity resolution tests (fixture-only)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from mbm.intake.identity import resolve_identity
from mbm.intake.normalization import normalize_manual_panel
from mbm.intake.types import IdentityStatus

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "cs2"


def _load(name: str):
    payload = json.loads((FIXTURES / name / "normalized.json").read_text(encoding="utf-8"))
    return normalize_manual_panel(payload)


class TestIntakeIdentity(unittest.TestCase):
    def test_eligible_resolves(self) -> None:
        env = resolve_identity(_load("eligible_headshots"))
        self.assertIs(env.identity_status, IdentityStatus.RESOLVED)

    def test_unresolved_roster(self) -> None:
        env = resolve_identity(_load("unresolved_identity"))
        self.assertIs(env.identity_status, IdentityStatus.UNRESOLVED)
        detail = env.source_attempts[-1].detail
        self.assertIn("roster", detail)


if __name__ == "__main__":
    unittest.main()
