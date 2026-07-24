#!/usr/bin/env python3
"""Report intake/scaffold vs Core acceptance. Skips never count as Core acceptance."""

from __future__ import annotations

import hashlib
import sys
import unittest
from io import StringIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from mbm.behavioral.adapters.cs2.projection import (  # noqa: E402
    CORE_WHEEL,
    EXPECTED_CORE_SHA256,
    core_ready,
    core_wheel_present,
)

INTAKE_PREFIXES = (
    "test_intake_",
    "test_cs2_headshots_gates",
    "test_core_gate",
    "test_cs2_vertical_slice.TestCs2Scaffold",
)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.discover(str(ROOT / "tests"), pattern="test_*.py")
    stream = StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)

    digest = None
    if core_wheel_present():
        digest = hashlib.sha256(CORE_WHEEL.read_bytes()).hexdigest()

    intake_failures = 0
    for test, _err in list(result.failures) + list(result.errors):
        name = test.id()
        if any(p in name for p in INTAKE_PREFIXES) or name.startswith("test_intake"):
            intake_failures += 1

    if core_ready():
        acc_suite = loader.loadTestsFromName(
            "test_cs2_vertical_slice.TestCs2VerticalSliceWithCore"
        )
        acc_stream = StringIO()
        acc_result = unittest.TextTestRunner(stream=acc_stream, verbosity=0).run(acc_suite)
        acceptance_ran = acc_result.testsRun
        acceptance_ok = (
            acc_result.testsRun
            - len(acc_result.failures)
            - len(acc_result.errors)
            - len(acc_result.skipped)
        )
        slice_complete = (
            acc_result.wasSuccessful()
            and acceptance_ran > 0
            and len(acc_result.skipped) == 0
        )
    else:
        acceptance_ran = 0
        acceptance_ok = 0
        slice_complete = False

    print(stream.getvalue())
    print("======== MBM-ESPORTS STATUS ========")
    print(f"wheel_present: {core_wheel_present()}")
    print(f"wheel_sha256:  {digest}")
    print(f"sha_expected:  {EXPECTED_CORE_SHA256}")
    print(f"core_ready:    {core_ready()}")
    print(f"tests_run:     {result.testsRun}")
    print(f"failures:      {len(result.failures)}")
    print(f"errors:        {len(result.errors)}")
    print(f"skipped:       {len(result.skipped)}")
    print(f"intake_failures:{intake_failures}")
    if core_ready():
        print(f"acceptance_ran:{acceptance_ran}")
        print(f"acceptance_ok: {acceptance_ok}")

    if slice_complete:
        print("RESULT: CS2 vertical slice ACCEPTANCE MET")
        return 0 if result.wasSuccessful() else 1

    print("RESULT: scaffold + intake complete / Core integration blocked")
    print("NOTE: Intake/gate passes do not count as Core vertical-slice acceptance.")
    print(
        "NOTE: Core-dependent skips do not count toward CS2 vertical-slice acceptance."
    )
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
