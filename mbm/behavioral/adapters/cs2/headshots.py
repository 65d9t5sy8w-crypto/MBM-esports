"""CS2 Maps 1–2 Headshots opportunity + conversion gates."""

from __future__ import annotations

from dataclasses import dataclass

from mbm.intake.evidence import (
    EvidenceAssessment,
    assess_evidence,
    explicit_pass_message,
    refuse_scope_blend,
)
from mbm.intake.identity import resolve_identity
from mbm.intake.types import (
    ALLOWED_ACTIONS,
    DEFAULT_MARKET_SCOPE,
    EvidenceEnvelope,
    MarketScope,
    Recommendation,
)

# Conversion: headshots / kills must clear this adjusted rate for OVER path support.
MIN_CONVERSION_RATE = 0.42
# Opportunity: mean Maps 1–2 kills must clear line / expected conversion.
KILL_SUPPORT_BUFFER = 0.0


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    detail: str
    value: float | None = None


@dataclass(frozen=True)
class HeadshotsDecision:
    action: Recommendation
    reasons: tuple[str, ...]
    opportunity: GateResult
    conversion: GateResult
    probabilities: dict[str, float]
    provenance: tuple[dict, ...]
    evidence: EvidenceEnvelope
    distribution_valid: bool

    def __post_init__(self) -> None:
        if self.action.value not in ALLOWED_ACTIONS:
            raise ValueError(f"invalid action {self.action}")
        if self.action.value == "WATCHLIST":
            raise ValueError("WATCHLIST is forbidden")


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _scoped_logs(envelope: EvidenceEnvelope) -> list:
    expected = envelope.fixture.market_scope
    blend = refuse_scope_blend((log.market_scope for log in envelope.match_logs), expected)
    if blend:
        return []
    return [log for log in envelope.match_logs if log.market_scope is expected]


def opportunity_gate(envelope: EvidenceEnvelope, line: float) -> GateResult:
    """Projected Maps 1–2 kills must support the headshots line."""
    if envelope.fixture.market_scope is not DEFAULT_MARKET_SCOPE:
        return GateResult(
            name="opportunity",
            passed=False,
            detail=(
                f"default CS2 headshots scope is {DEFAULT_MARKET_SCOPE.value}; "
                f"got {envelope.fixture.market_scope.value}"
            ),
        )
    logs = _scoped_logs(envelope)
    if not logs:
        return GateResult(
            name="opportunity",
            passed=False,
            detail="no Maps 1–2 kill samples after scope check",
        )
    mean_kills = _mean([log.kills for log in logs])
    # Line is headshots; required kills ≈ line / min conversion.
    required_kills = line / MIN_CONVERSION_RATE if MIN_CONVERSION_RATE else line
    passed = mean_kills + KILL_SUPPORT_BUFFER >= required_kills
    return GateResult(
        name="opportunity",
        passed=passed,
        detail=(
            f"mean_maps_1_2_kills={mean_kills:.3f} "
            f"required_kills_for_line={required_kills:.3f} line={line}"
        ),
        value=mean_kills,
    )


def conversion_gate(envelope: EvidenceEnvelope, line: float) -> GateResult:
    """Adjusted headshot rate must clear required conversion."""
    logs = _scoped_logs(envelope)
    if not logs:
        return GateResult(
            name="conversion",
            passed=False,
            detail="no Maps 1–2 headshot samples after scope check",
        )
    total_kills = sum(log.kills for log in logs)
    total_hs = sum(log.headshots for log in logs)
    rate = (total_hs / total_kills) if total_kills > 0 else 0.0
    mean_hs = _mean([log.headshots for log in logs])
    # Conversion clears rate threshold AND projected HS supports line directionally.
    rate_ok = rate >= MIN_CONVERSION_RATE
    volume_ok = mean_hs > 0
    passed = rate_ok and volume_ok
    return GateResult(
        name="conversion",
        passed=passed,
        detail=(
            f"adjusted_hs_rate={rate:.3f} min_rate={MIN_CONVERSION_RATE} "
            f"mean_maps_1_2_hs={mean_hs:.3f} line={line}"
        ),
        value=rate,
    )


def _distribution(action: Recommendation, confidence: float) -> dict[str, float]:
    confidence = min(max(confidence, 0.0), 0.95)
    residual = 1.0 - confidence
    if action is Recommendation.PASS:
        return {"OVER": residual / 2.0, "UNDER": residual / 2.0, "PASS": confidence}
    if action is Recommendation.OVER:
        return {"OVER": confidence, "UNDER": residual * 0.35, "PASS": residual * 0.65}
    return {"UNDER": confidence, "OVER": residual * 0.35, "PASS": residual * 0.65}


def _validate_distribution(probs: dict[str, float]) -> bool:
    if set(probs) != ALLOWED_ACTIONS:
        return False
    if any(v < 0 for v in probs.values()):
        return False
    return abs(sum(probs.values()) - 1.0) <= 1e-9


def evaluate_headshots(
    envelope: EvidenceEnvelope,
    *,
    now=None,
) -> HeadshotsDecision:
    """Run identity → evidence → opportunity/conversion; emit OVER/UNDER/PASS."""
    resolved = resolve_identity(envelope)
    assessment: EvidenceAssessment = assess_evidence(resolved, now=now)

    line_obj = next((m for m in assessment.envelope.market_lines if m.stat == "headshots"), None)
    line = line_obj.line if line_obj else float("nan")

    if not assessment.actionable or line_obj is None:
        reasons = list(assessment.reasons)
        if line_obj is None:
            reasons.append("headshots market line missing")
        opp = GateResult("opportunity", False, "skipped: evidence not actionable")
        conv = GateResult("conversion", False, "skipped: evidence not actionable")
        probs = _distribution(Recommendation.PASS, 0.8)
        msg = explicit_pass_message(reasons, assessment.envelope.source_attempts)
        return HeadshotsDecision(
            action=Recommendation.PASS,
            reasons=(msg,),
            opportunity=opp,
            conversion=conv,
            probabilities=probs,
            provenance=tuple(p.__dict__ for p in assessment.envelope.provenance),
            evidence=assessment.envelope,
            distribution_valid=_validate_distribution(probs),
        )

    if line_obj.market_scope is not MarketScope.MAPS_1_2:
        reasons = (
            f"PASS: refusing scope blend/non-default scope {line_obj.market_scope.value}",
        )
        probs = _distribution(Recommendation.PASS, 0.85)
        return HeadshotsDecision(
            action=Recommendation.PASS,
            reasons=reasons,
            opportunity=GateResult("opportunity", False, reasons[0]),
            conversion=GateResult("conversion", False, reasons[0]),
            probabilities=probs,
            provenance=tuple(p.__dict__ for p in assessment.envelope.provenance),
            evidence=assessment.envelope,
            distribution_valid=_validate_distribution(probs),
        )

    opp = opportunity_gate(assessment.envelope, line)
    conv = conversion_gate(assessment.envelope, line)

    if not opp.passed or not conv.passed:
        fail_reasons = []
        if not opp.passed:
            fail_reasons.append(f"opportunity gate failed: {opp.detail}")
        if not conv.passed:
            fail_reasons.append(f"conversion gate failed: {conv.detail}")
        msg = explicit_pass_message(fail_reasons, assessment.envelope.source_attempts)
        probs = _distribution(Recommendation.PASS, 0.75)
        return HeadshotsDecision(
            action=Recommendation.PASS,
            reasons=(msg,),
            opportunity=opp,
            conversion=conv,
            probabilities=probs,
            provenance=tuple(p.__dict__ for p in assessment.envelope.provenance),
            evidence=assessment.envelope,
            distribution_valid=_validate_distribution(probs),
        )

    logs = _scoped_logs(assessment.envelope)
    mean_hs = _mean([log.headshots for log in logs])
    if mean_hs > line:
        action = Recommendation.OVER
        confidence = min(0.55 + (mean_hs - line) / max(line, 1.0) * 0.2, 0.85)
    elif mean_hs < line:
        action = Recommendation.UNDER
        confidence = min(0.55 + (line - mean_hs) / max(line, 1.0) * 0.2, 0.85)
    else:
        action = Recommendation.PASS
        confidence = 0.7

    probs = _distribution(action, confidence)
    reasons: tuple[str, ...]
    if action is Recommendation.PASS:
        reasons = ("PASS: projected Maps 1–2 headshots equal line; no edge",)
    else:
        reasons = (
            f"{action.value}: mean_maps_1_2_hs={mean_hs:.3f} line={line}; "
            f"{opp.detail}; {conv.detail}",
        )

    return HeadshotsDecision(
        action=action,
        reasons=reasons,
        opportunity=opp,
        conversion=conv,
        probabilities=probs,
        provenance=tuple(p.__dict__ for p in assessment.envelope.provenance),
        evidence=assessment.envelope,
        distribution_valid=_validate_distribution(probs),
    )
