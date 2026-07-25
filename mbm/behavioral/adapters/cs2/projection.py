"""CS2 Maps 1–2 Headshots projection entrypoint.

Intake path evaluates evidence + gates without Core.
Authentic Core v0.1.0 thin-panel projection never invents calibrated confidence.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any, Callable

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

_REQUIRED_PLAYER_FIELDS = ("kill_share", "stability", "eco_dependency")

CORE_DISTRIBUTION_UNAVAILABLE = "CORE_DISTRIBUTION_UNAVAILABLE"
MISSING_PLAYER_LEVEL_CORE_INPUTS = "MISSING_PLAYER_LEVEL_CORE_INPUTS"


class CoreDependencyBlocked(RuntimeError):
    """Raised when authentic MBM Core v0.1.0 is not available."""


@dataclass(frozen=True)
class ProvenanceItem:
    name: str
    value: Any


@dataclass(frozen=True)
class PublicationDecision:
    eligible: bool
    action: str
    reason: str


@dataclass(frozen=True)
class ProjectionResult:
    probabilities: dict[str, float]
    provenance: tuple[ProvenanceItem, ...]
    decision: PublicationDecision
    scores: dict[str, float]
    core_label: str


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


def _core_install_root() -> Path:
    try:
        dist = distribution("mbm-core")
    except PackageNotFoundError as exc:
        raise CoreDependencyBlocked(
            "Authentic Core wheel is verified on disk but mbm-core is not installed. "
            "Install via the repository Core pin in pyproject.toml."
        ) from exc
    return Path(dist.locate_file(""))


def _ensure_mbm_core_package() -> None:
    """Expose installed mbm.core despite local mbm package shadowing."""
    if "mbm.core.scoring" in sys.modules and "mbm.core.classifier" in sys.modules:
        return

    core_dir = _core_install_root() / "mbm" / "core"
    init_py = core_dir / "__init__.py"
    if not init_py.is_file() or not (core_dir / "scoring.py").is_file():
        raise CoreDependencyBlocked(
            "Authentic Core install is missing mbm.core modules "
            f"under {_core_install_root() / 'mbm' / 'core'}."
        )

    import mbm as mbm_pkg

    if "mbm.core" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "mbm.core",
            init_py,
            submodule_search_locations=[str(core_dir)],
        )
        if spec is None or spec.loader is None:
            raise CoreDependencyBlocked("Unable to construct import spec for mbm.core.")
        module = importlib.util.module_from_spec(spec)
        sys.modules["mbm.core"] = module
        setattr(mbm_pkg, "core", module)
        spec.loader.exec_module(module)

    importlib.import_module("mbm.core.scoring")
    importlib.import_module("mbm.core.classifier")


def _load_core_api() -> tuple[
    Callable[[dict[str, float]], dict[str, float]],
    Callable[[dict[str, float]], str],
]:
    require_core()
    try:
        _ensure_mbm_core_package()
        scoring = importlib.import_module("mbm.core.scoring")
        classifier = importlib.import_module("mbm.core.classifier")
        compute_scores = getattr(scoring, "compute_scores")
        classify_player = getattr(classifier, "classify_player")
    except CoreDependencyBlocked:
        raise
    except Exception as exc:  # noqa: BLE001 — fail closed on any Core import failure
        raise CoreDependencyBlocked(
            f"Core wheel verified but mbm.core import is not usable: {exc}"
        ) from exc
    if not callable(compute_scores) or not callable(classify_player):
        raise CoreDependencyBlocked(
            "mbm.core is imported but compute_scores/classify_player are not usable."
        )
    return compute_scores, classify_player


def _extract_player_level_core_inputs(
    panel: CS2HeadshotsPanel,
) -> tuple[dict[str, float] | None, tuple[str, ...]]:
    """Require verified player-level Core inputs; never derive kill_share from team averages."""
    features = panel.features
    missing: list[str] = []
    player: dict[str, float] = {}
    for field in _REQUIRED_PLAYER_FIELDS:
        if field not in features:
            missing.append(field)
            continue
        try:
            player[field] = float(features[field])
        except (TypeError, ValueError):
            missing.append(field)
    if missing:
        return None, tuple(missing)
    return player, ()


def _ineligible_result(
    panel: CS2HeadshotsPanel,
    *,
    reason: str,
    extra_provenance: tuple[ProvenanceItem, ...] = (),
    scores: dict[str, float] | None = None,
    core_label: str = "",
) -> ProjectionResult:
    return ProjectionResult(
        probabilities={},
        provenance=tuple(
            ProvenanceItem(name=name, value=value) for name, value in panel.features.items()
        )
        + extra_provenance,
        decision=PublicationDecision(
            eligible=False,
            action="PASS",
            reason=reason,
        ),
        scores=dict(scores or {}),
        core_label=core_label,
    )


def project_headshots_from_envelope(
    envelope: EvidenceEnvelope,
    *,
    now=None,
) -> HeadshotsDecision:
    """Provider-neutral intake projection (no PandaScore, no Core required)."""
    return evaluate_headshots(envelope, now=now)


def project_maps_1_2_headshots(panel: CS2HeadshotsPanel) -> ProjectionResult:
    """Score verified player-level Core inputs, then fail closed without calibrated mass."""
    if panel.market is not CS2MarketKey.MAPS_1_2_HEADSHOTS:
        raise ValueError(f"unsupported market: {panel.market}")
    if panel.map_window.start_map != 1 or panel.map_window.end_map != 2:
        raise ValueError("this slice only supports maps 1–2")

    compute_scores, classify_player = _load_core_api()
    player, missing = _extract_player_level_core_inputs(panel)
    if player is None:
        return _ineligible_result(
            panel,
            reason=MISSING_PLAYER_LEVEL_CORE_INPUTS,
            extra_provenance=(
                ProvenanceItem(name="missing_player_level_core_inputs", value=list(missing)),
                ProvenanceItem(name="refused_team_average_as_kill_share", value=True),
            ),
        )

    scores = compute_scores(player)
    core_label = str(classify_player(scores))
    return _ineligible_result(
        panel,
        reason=CORE_DISTRIBUTION_UNAVAILABLE,
        extra_provenance=(
            ProvenanceItem(name="core_player_inputs", value=dict(player)),
            ProvenanceItem(name="core_scores", value=dict(scores)),
            ProvenanceItem(name="core_label", value=core_label),
            ProvenanceItem(name="core_distribution", value=CORE_DISTRIBUTION_UNAVAILABLE),
        ),
        scores=dict(scores),
        core_label=core_label,
    )


# Re-export pin helpers for existing tests/scripts.
__all__ = [
    "ALLOWED_ACTIONS",
    "CORE_DISTRIBUTION_UNAVAILABLE",
    "CORE_WHEEL",
    "EXPECTED_CORE_SHA256",
    "MISSING_PLAYER_LEVEL_CORE_INPUTS",
    "CoreDependencyBlocked",
    "ProjectionResult",
    "PublicationDecision",
    "ProvenanceItem",
    "core_ready",
    "core_wheel_present",
    "core_wheel_sha256",
    "project_headshots_from_envelope",
    "project_maps_1_2_headshots",
    "require_core",
]
