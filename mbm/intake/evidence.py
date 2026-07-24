"""Provenance, source-attempt ledger, staleness, explicit PASS reasons."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Iterable

from mbm.intake.types import (
    DEFAULT_MARKET_SCOPE,
    EvidenceEnvelope,
    EvidenceStatus,
    IdentityStatus,
    MarketScope,
    ProvenanceItem,
    Recommendation,
    SourceAttempt,
)

# Evidence older than this is treated as stale for live projection.
DEFAULT_STALE_HOURS = 72.0
MIN_MATCH_LOGS = 10


@dataclass(frozen=True)
class EvidenceAssessment:
    envelope: EvidenceEnvelope
    actionable: bool
    recommendation_if_blocked: Recommendation
    reasons: tuple[str, ...]


def _parse_iso(ts: str) -> datetime:
    text = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_stale(
    envelope: EvidenceEnvelope,
    *,
    now: datetime | None = None,
    max_age_hours: float = DEFAULT_STALE_HOURS,
) -> bool:
    now = now or datetime.now(timezone.utc)
    captured = _parse_iso(envelope.captured_at)
    age_hours = (now - captured.astimezone(timezone.utc)).total_seconds() / 3600.0
    return age_hours > max_age_hours


def headshots_completeness(envelope: EvidenceEnvelope) -> dict[str, bool]:
    scope = envelope.fixture.market_scope
    scoped_logs = [log for log in envelope.match_logs if log.market_scope is scope]
    has_line = any(m.stat == "headshots" for m in envelope.market_lines)
    kills_sample = len(scoped_logs) >= MIN_MATCH_LOGS and all(log.kills >= 0 for log in scoped_logs)
    hs_sample = len(scoped_logs) >= MIN_MATCH_LOGS and all(log.headshots >= 0 for log in scoped_logs)
    return {
        "resolved_identity": envelope.identity_status is IdentityStatus.RESOLVED,
        "market_scope_maps_1_2": scope is DEFAULT_MARKET_SCOPE,
        "headshots_line_present": has_line,
        "maps_1_2_kills_sample": kills_sample,
        "maps_1_2_hs_sample": hs_sample,
        "min_match_logs": len(scoped_logs) >= MIN_MATCH_LOGS,
        "map_context_present": bool(envelope.map_context),
    }


def refuse_scope_blend(logs_scopes: Iterable[MarketScope], expected: MarketScope) -> str | None:
    scopes = set(logs_scopes)
    if not scopes:
        return "no match_logs for expected market scope"
    if scopes != {expected}:
        return (
            f"refusing silent scope blend: found {[s.value for s in sorted(scopes, key=lambda s: s.value)]} "
            f"expected only {expected.value}"
        )
    return None


def assess_evidence(
    envelope: EvidenceEnvelope,
    *,
    now: datetime | None = None,
    max_age_hours: float = DEFAULT_STALE_HOURS,
    approved_sources_attempted: Iterable[str] | None = None,
) -> EvidenceAssessment:
    """Evaluate readiness. Never returns a generic 'data unavailable' reason."""
    attempts = list(envelope.source_attempts)
    if approved_sources_attempted:
        for src in approved_sources_attempted:
            if not any(a.source == src for a in attempts):
                attempts.append(
                    SourceAttempt(
                        source=src,
                        outcome="attempted",
                        detail="approved source checked before unknown",
                    )
                )

    reasons: list[str] = []
    status = envelope.evidence_status

    # Surface provider unavailability on the PASS decision itself (not only the ledger).
    for a in attempts:
        if a.outcome == "unavailable" and a.detail and a.detail not in reasons:
            reasons.append(a.detail)

    if envelope.identity_status is not IdentityStatus.RESOLVED:
        reasons.append("identity unresolved before scoring")

    if is_stale(envelope, now=now, max_age_hours=max_age_hours):
        reasons.append(
            f"evidence stale: captured_at={envelope.captured_at} exceeds {max_age_hours}h"
        )
        status = EvidenceStatus.STALE

    blend = refuse_scope_blend(
        (log.market_scope for log in envelope.match_logs),
        envelope.fixture.market_scope,
    )
    # Allow empty logs to be reported via completeness rather than blend when none present.
    if envelope.match_logs and blend:
        reasons.append(blend)

    completeness = headshots_completeness(
        replace(envelope, identity_status=envelope.identity_status)
    )
    for key, ok in completeness.items():
        if not ok:
            reasons.append(f"evidence incomplete: {key}=false")

    if reasons and status is EvidenceStatus.VERIFIED:
        status = (
            EvidenceStatus.UNRESOLVED
            if envelope.identity_status is IdentityStatus.UNRESOLVED
            else EvidenceStatus.INCOMPLETE
        )
        if any(r.startswith("evidence stale") for r in reasons):
            status = EvidenceStatus.STALE

    provenance = list(envelope.provenance)
    provenance.append(
        ProvenanceItem(
            name="evidence_completeness",
            source="intake.evidence",
            value=completeness,
        )
    )
    provenance.append(
        ProvenanceItem(
            name="source_attempts",
            source="intake.evidence",
            value=[a.__dict__ for a in attempts],
        )
    )
    if reasons:
        provenance.append(
            ProvenanceItem(
                name="pass_reasons",
                source="intake.evidence",
                value=reasons,
            )
        )
        attempts.append(
            SourceAttempt(
                source="intake.evidence",
                outcome="blocked",
                detail="; ".join(reasons),
            )
        )
    else:
        attempts.append(
            SourceAttempt(
                source="intake.evidence",
                outcome="ready",
                detail="identity resolved; evidence complete; not stale",
            )
        )

    updated = replace(
        envelope,
        evidence_status=status,
        evidence_completeness=completeness,
        provenance=provenance,
        source_attempts=attempts,
    )
    actionable = not reasons
    return EvidenceAssessment(
        envelope=updated,
        actionable=actionable,
        recommendation_if_blocked=Recommendation.PASS,
        reasons=tuple(reasons),
    )


def explicit_pass_message(reasons: Iterable[str], attempts: Iterable[SourceAttempt]) -> str:
    """Format PASS detail. Never use generic 'data unavailable'."""
    reason_list = list(reasons)
    if not reason_list:
        raise ValueError("explicit PASS requires at least one concrete reason")
    if any("data unavailable" in r.lower() for r in reason_list):
        raise ValueError("generic 'data unavailable' is forbidden")
    attempt_bits = [f"{a.source}:{a.outcome}" for a in attempts]
    return (
        "PASS: "
        + "; ".join(reason_list)
        + " | sources_attempted="
        + ",".join(attempt_bits)
    )
