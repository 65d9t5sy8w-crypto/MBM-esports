"""Resolve fixture, teams, player, roster, opponent, and market scope."""

from __future__ import annotations

from dataclasses import replace

from mbm.intake.types import (
    DEFAULT_MARKET_SCOPE,
    EvidenceEnvelope,
    IdentityStatus,
    MarketScope,
    ProvenanceItem,
    SourceAttempt,
)


def resolve_identity(envelope: EvidenceEnvelope) -> EvidenceEnvelope:
    """Mark identity resolved only when critical fields are present and consistent."""
    attempts = list(envelope.source_attempts)
    reasons: list[str] = []

    fixture = envelope.fixture
    if not fixture.event_id:
        reasons.append("fixture.event_id missing")
    if not fixture.team_a or not fixture.team_b:
        reasons.append("fixture teams unresolved")
    if not fixture.start_time:
        reasons.append("fixture.start_time missing")
    if not fixture.format:
        reasons.append("fixture.format missing")

    if fixture.market_scope is not DEFAULT_MARKET_SCOPE:
        # Scope may be non-default only when explicitly set; still must be known.
        if fixture.market_scope not in MarketScope:
            reasons.append("fixture.market_scope invalid")

    if not envelope.players:
        reasons.append("roster empty")
    else:
        teams = {p.team for p in envelope.players if p.team}
        if fixture.team_a and fixture.team_a not in teams:
            reasons.append(f"roster missing team_a={fixture.team_a}")
        if fixture.team_b and fixture.team_b not in teams:
            reasons.append(f"roster missing team_b={fixture.team_b}")

    target = envelope.target_player_id
    if not target:
        reasons.append("target_player_id unresolved")
    else:
        ids = {p.player_id for p in envelope.players}
        if target not in ids:
            reasons.append(f"target player {target} not on roster")

    if not envelope.market_lines:
        reasons.append("market_lines missing")
    else:
        line = envelope.market_lines[0]
        if line.market_scope != fixture.market_scope:
            reasons.append(
                f"market scope mismatch: line={line.market_scope.value} "
                f"fixture={fixture.market_scope.value}"
            )
        if target and line.player_id and line.player_id != target:
            reasons.append("market_line.player_id does not match target_player_id")

    attempts.append(
        SourceAttempt(
            source="identity.resolver",
            outcome="resolved" if not reasons else "unresolved",
            detail="; ".join(reasons) if reasons else "fixture/teams/player/roster/scope ok",
        )
    )

    provenance = list(envelope.provenance)
    provenance.append(
        ProvenanceItem(
            name="identity_status",
            source="identity.resolver",
            value=IdentityStatus.RESOLVED.value if not reasons else IdentityStatus.UNRESOLVED.value,
        )
    )
    if reasons:
        provenance.append(
            ProvenanceItem(
                name="identity_failure_reasons",
                source="identity.resolver",
                value=reasons,
            )
        )

    return replace(
        envelope,
        identity_status=IdentityStatus.RESOLVED if not reasons else IdentityStatus.UNRESOLVED,
        source_attempts=attempts,
        provenance=provenance,
    )
