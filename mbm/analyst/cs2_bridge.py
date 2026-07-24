"""Bridge CS2 headshots evaluation → canonical analyst decision.

Not imported by mbm.dashboard (keeps UI free of adapter types).
"""

from __future__ import annotations

from datetime import datetime

from mbm.analyst.decision import CanonicalDecision
from mbm.analyst.models import GateView
from mbm.behavioral.adapters.cs2.headshots import evaluate_headshots
from mbm.intake.types import EvidenceEnvelope, EvidenceStatus, IdentityStatus


def decide_headshots(envelope: EvidenceEnvelope, *, now: datetime | None = None) -> CanonicalDecision:
    result = evaluate_headshots(envelope, now=now)
    assessed = result.evidence
    identity_notes: list[str] = []
    for item in assessed.provenance:
        if item.name == "identity_failure_reasons" and isinstance(item.value, list):
            identity_notes.extend(str(v) for v in item.value)

    actionable = (
        assessed.identity_status is IdentityStatus.RESOLVED
        and assessed.evidence_status is EvidenceStatus.VERIFIED
        and all(assessed.evidence_completeness.values())
        if assessed.evidence_completeness
        else False
    )
    # Gate-only PASS still had actionable evidence
    if "skipped: evidence not actionable" in result.opportunity.detail:
        actionable = False
    elif result.opportunity.name == "opportunity" and "skipped:" not in result.opportunity.detail:
        if assessed.identity_status is IdentityStatus.RESOLVED and assessed.evidence_status is EvidenceStatus.VERIFIED:
            actionable = True

    return CanonicalDecision(
        action=result.action,
        reasons=result.reasons,
        opportunity=GateView(
            result.opportunity.name,
            result.opportunity.passed,
            result.opportunity.detail,
            result.opportunity.value,
        ),
        conversion=GateView(
            result.conversion.name,
            result.conversion.passed,
            result.conversion.detail,
            result.conversion.value,
        ),
        probabilities=dict(result.probabilities),
        provenance=tuple(result.provenance),
        evidence_status=assessed.evidence_status.value,
        identity_status=assessed.identity_status.value,
        identity_notes=tuple(identity_notes),
        raw_refs=(assessed.raw_ref,) if assessed.raw_ref else (),
        map_context=dict(assessed.map_context),
        actionable=actionable,
    )
