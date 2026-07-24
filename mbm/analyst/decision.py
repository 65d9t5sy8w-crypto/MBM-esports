"""Canonical projection decision consumed by the analyst board."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from mbm.analyst.models import GateView
from mbm.intake.types import EvidenceEnvelope, Recommendation


@dataclass(frozen=True)
class CanonicalDecision:
    action: Recommendation
    reasons: tuple[str, ...]
    opportunity: GateView
    conversion: GateView
    probabilities: dict[str, float]
    provenance: tuple[dict[str, Any], ...]
    evidence_status: str
    identity_status: str
    identity_notes: tuple[str, ...]
    raw_refs: tuple[str, ...]
    map_context: dict[str, Any]
    actionable: bool


class DecisionProvider(Protocol):
    def __call__(self, envelope: EvidenceEnvelope) -> CanonicalDecision: ...


DecideFn = Callable[[EvidenceEnvelope], CanonicalDecision]
