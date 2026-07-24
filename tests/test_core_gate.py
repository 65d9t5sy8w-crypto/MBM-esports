"""Hard gate: never treat a missing Core wheel as installed/verified."""

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "vendor" / "mbm-core"
WHEEL = VENDOR / "mbm_core-0.1.0-py3-none-any.whl"
BLOCKED = VENDOR / "BLOCKED"
EXPECTED_SHA256 = "d151b045fcfa9dd5225cd040740a5f246772bb14ceae5f10c16ff5b3fbf20151"


class TestCoreGate(unittest.TestCase):
    def test_blocked_marker_present_while_wheel_absent(self) -> None:
        if WHEEL.is_file():
            self.skipTest("wheel present; blocked marker may be removed after verify")
        self.assertTrue(BLOCKED.is_file(), "vendor/mbm-core/BLOCKED must exist")

    def test_no_substitute_wheel_without_checksum_match(self) -> None:
        if not WHEEL.is_file():
            self.assertFalse(WHEEL.is_file())
            return
        digest = hashlib.sha256(WHEEL.read_bytes()).hexdigest()
        self.assertEqual(
            digest,
            EXPECTED_SHA256,
            "vendored wheel SHA-256 must match the authentic v0.1.0 artifact",
        )


if __name__ == "__main__":
    unittest.main()
