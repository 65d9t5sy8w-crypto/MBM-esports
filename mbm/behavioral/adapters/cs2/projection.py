"""CS2 Maps 1–2 Headshots projection entrypoint.

Intake path evaluates evidence + gates without Core.
Core-backed ProjectionResult remains blocked until the authentic wheel is present.
"""

from __future__ import annotations

from typing import Any

from mbm.behavioral.adapters.cs2.headshots import HeadshotsDecision, evaluate_headshots
from mbm.behavioral.adapters.cs2.types import CS2HeadshotsPanel, CS2MarketKey
from mbm.core_pin import (
    EXPECTED_CORE_SHA256,
    core_ready,
    core_wheel_path,
    core_wheel_present,
    core_wheel_sha256,
)
from mbm.intake.types import ALLOWED_ACTIONS, EvidenceEnvelope

CORE_WHEEL = core_wheel_path()


class CoreDependencyBlocked(RuntimeError):
    """Raised when authentic MBM Core v0.1.0 is not available."""


def require_core() -> None:
    if not core_wheel_present():
        raise CoreDependencyBlocked(
            "MBM Core v0.1.0 is BLOCKED: place the authentic wheel at "
            f"{CORE_WHEEL} (SHA-256 {EXPECTED_CORE_SHA256}) before projecting. "
            "Do not reconstruct a substitute wheel."
        )
    digest = core_wheel_sha256()
    if digest != EXPECTED_CORE_SHA256:
        raise CoreDependencyBlocked(
            f"MBM Core wheel SHA-256 mismatch: got {digest}, "
            f"expected {EXPECTED_CORE_SHA256}. Refusing substitute artifact."
        )


def project_headshots_from_envelope(
    envelope: EvidenceEnvelope,
    *,
    now=None,
) -> HeadshotsDecision:
    """Provider-neutral intake projection (no PandaScore, no Core required)."""
    return evaluate_headshots(envelope, now=now)


def project_maps_1_2_headshots(panel: CS2HeadshotsPanel) -> Any:
    """Legacy Core path for thin panels. Requires authentic MBM Core."""
    if panel.market is not CS2MarketKey.MAPS_1_2_HEADSHOTS:
        raise ValueError(f"unsupported market: {panel.market}")
    if panel.map_window.start_map != 1 or panel.map_window.end_map != 2:
        raise ValueError("this slice only supports maps 1–2")

    require_core()

    raise CoreDependencyBlocked(
        "Core wheel file is present but import wiring is deferred until "
        "checksum verification is completed in a follow-up step."
    )


# Re-export pin helpers for existing tests/scripts.
__all__ = [
    "ALLOWED_ACTIONS",
    "CORE_WHEEL",
    "EXPECTED_CORE_SHA256",
    "CoreDependencyBlocked",
    "core_ready",
    "core_wheel_present",
    "core_wheel_sha256",
    "project_headshots_from_envelope",
    "project_maps_1_2_headshots",
    "require_core",
]
