"""Bridge NBA prop evaluation → canonical analyst decision.

Maps MORE/LESS → OVER/UNDER for the shared board while preserving NBA semantics
in map_context. Dashboard package must not import this module.
"""

from __future__ import annotations

from mbm.analyst.decision import CanonicalDecision
from mbm.analyst.models import GateView
from mbm.behavioral.adapters.nba.gates import evaluate_nba_prop
from mbm.behavioral.adapters.nba.leakage import PointInTimeCutoff
from mbm.behavioral.adapters.nba.types import NbaRecommendation
from mbm.intake.types import EvidenceEnvelope, Recommendation


def _to_shared(action: NbaRecommendation) -> Recommendation:
    if action is NbaRecommendation.MORE:
        return Recommendation.OVER
    if action is NbaRecommendation.LESS:
        return Recommendation.UNDER
    return Recommendation.PASS


def decide_nba_prop(
    envelope: EvidenceEnvelope,
    *,
    cutoff: PointInTimeCutoff | None = None,
) -> CanonicalDecision:
    result = evaluate_nba_prop(envelope, cutoff=cutoff)
    shared = _to_shared(result.action)
    probs = {
        Recommendation.OVER.value: result.probabilities.get("MORE", 0.0),
        Recommendation.UNDER.value: result.probabilities.get("LESS", 0.0),
        Recommendation.PASS.value: result.probabilities.get("PASS", 0.0),
    }
    ctx = dict(envelope.map_context)
    ctx["nba_action"] = result.action.value
    ctx["nba_grade"] = result.grade
    ctx["point_in_time_cutoff"] = {
        "game_id": result.cutoff.game_id,
        "game_start": result.cutoff.game_start,
        "as_of": result.cutoff.as_of,
        "recorded_at": result.cutoff.recorded_at,
    }
    ctx["market_notes"] = list(result.market_notes)
    ctx["certification_gate"] = result.certification_gate.detail

    actionable = (
        result.evidence_gate.passed
        and result.research_gate.passed
        and result.action is not NbaRecommendation.PASS
    )

    return CanonicalDecision(
        action=shared,
        reasons=result.reasons,
        opportunity=GateView(
            result.research_gate.name,
            result.research_gate.passed,
            result.research_gate.detail,
            result.research_gate.value,
        ),
        conversion=GateView(
            result.certification_gate.name,
            result.certification_gate.passed,
            result.certification_gate.detail,
            result.certification_gate.value,
        ),
        probabilities=probs,
        provenance=result.provenance,
        evidence_status=envelope.evidence_status.value,
        identity_status=envelope.identity_status.value,
        identity_notes=(),
        raw_refs=(envelope.raw_ref,) if envelope.raw_ref else (),
        map_context=ctx,
        actionable=actionable,
    )
