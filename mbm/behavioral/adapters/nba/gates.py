"""NBA evidence-quality, one-selection-per-game, and A-tier certification gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from mbm.behavioral.adapters.nba.analysis import (
    PlayerGameStat,
    research_bundle,
    stats_from_envelope_context,
)
from mbm.behavioral.adapters.nba.leakage import (
    PointInTimeCutoff,
    ensure_cutoff_recorded,
    market_snapshot_usable,
    parse_iso,
)
from mbm.behavioral.adapters.nba.projection import compare_to_market
from mbm.behavioral.adapters.nba.props import prop_probabilities
from mbm.behavioral.adapters.nba.types import (
    ALLOWED_NBA_ACTIONS,
    MarketSnapshot,
    NbaRecommendation,
    PropProbability,
)
from mbm.intake.types import EvidenceEnvelope, EvidenceStatus, IdentityStatus

# A-tier: high confidence + complete evidence + Core-ready handled upstream.
A_TIER_MIN_PROB = 0.70
MIN_RESEARCH_SAMPLE = 5


@dataclass(frozen=True)
class NbaGateResult:
    name: str
    passed: bool
    detail: str
    value: float | None = None


@dataclass(frozen=True)
class NbaPropDecision:
    action: NbaRecommendation
    reasons: tuple[str, ...]
    evidence_gate: NbaGateResult
    research_gate: NbaGateResult
    certification_gate: NbaGateResult
    probabilities: dict[str, float]
    prop: PropProbability
    grade: str
    cutoff: PointInTimeCutoff
    market_notes: tuple[str, ...]
    provenance: tuple[dict, ...]

    def __post_init__(self) -> None:
        if self.action.value not in ALLOWED_NBA_ACTIONS:
            raise ValueError(f"invalid NBA action {self.action}")


def _snapshots_from_envelope(envelope: EvidenceEnvelope) -> list[MarketSnapshot]:
    out: list[MarketSnapshot] = []
    for row in envelope.map_context.get("player_props") or []:
        if not isinstance(row, dict):
            continue
        market = row.get("market") if isinstance(row.get("market"), dict) else {}
        try:
            line = float(row.get("line_value"))
        except (TypeError, ValueError):
            continue
        more_odds = None
        less_odds = None
        if str(market.get("type") or "") == "over_under" or "over_odds" in market:
            more_odds = market.get("over_odds")
            less_odds = market.get("under_odds")
            try:
                more_odds = int(more_odds) if more_odds is not None else None
                less_odds = int(less_odds) if less_odds is not None else None
            except (TypeError, ValueError):
                more_odds, less_odds = None, None
        captured = str(row.get("updated_at") or row.get("captured_at") or "")
        if not captured:
            continue
        out.append(
            MarketSnapshot(
                vendor=str(row.get("vendor") or "unknown"),
                prop_type=str(row.get("prop_type") or "unknown"),
                line=line,
                more_odds=more_odds,
                less_odds=less_odds,
                captured_at=captured,
                source_identity="balldontlie",
                raw_evidence_ref=f"player_prop:{row.get('id')}",
                game_id=str(row.get("game_id") or ""),
            )
        )
    # Game totals / spreads as sportsbook prices with source identity.
    for row in envelope.map_context.get("sportsbook_prices") or []:
        if not isinstance(row, dict):
            continue
        captured = str(row.get("updated_at") or "")
        if not captured:
            continue
        total = row.get("total_value")
        if total is None:
            continue
        try:
            line = float(total)
        except (TypeError, ValueError):
            continue
        out.append(
            MarketSnapshot(
                vendor=str(row.get("vendor") or "unknown"),
                prop_type="total_points",
                line=line,
                more_odds=row.get("total_over_odds"),
                less_odds=row.get("total_under_odds"),
                captured_at=captured,
                source_identity=str(row.get("source_identity") or "balldontlie"),
                raw_evidence_ref=str(row.get("raw_evidence_ref") or "odds"),
                game_id=str(row.get("game_id") or ""),
            )
        )
    return out


def evidence_quality_gate(envelope: EvidenceEnvelope) -> NbaGateResult:
    reasons: list[str] = []
    if envelope.identity_status is not IdentityStatus.RESOLVED:
        reasons.append(f"identity={envelope.identity_status.value}")
    if envelope.evidence_status in {EvidenceStatus.STALE, EvidenceStatus.UNRESOLVED}:
        reasons.append(f"evidence_status={envelope.evidence_status.value}")
    if envelope.map_context.get("not_for_projection"):
        reasons.append("not_for_projection")
    if not envelope.fixture.team_a or not envelope.fixture.team_b:
        reasons.append("missing_teams")
    passed = not reasons
    return NbaGateResult(
        name="evidence_quality",
        passed=passed,
        detail="ok" if passed else "; ".join(reasons),
    )


def one_selection_per_game(
    candidates: Sequence[NbaPropDecision],
) -> list[NbaPropDecision]:
    """Enforce MBM one-selection-per-game: keep highest-grade non-PASS per event."""
    by_game: dict[str, list[NbaPropDecision]] = {}
    for c in candidates:
        by_game.setdefault(c.cutoff.game_id, []).append(c)

    grade_rank = {"A": 3, "B": 2, "C": 1, "D": 0, "PASS": -1}
    selected: list[NbaPropDecision] = []
    for _gid, rows in by_game.items():
        actionable = [r for r in rows if r.action is not NbaRecommendation.PASS]
        if not actionable:
            # Keep a single PASS representative.
            selected.append(rows[0])
            continue
        actionable.sort(
            key=lambda r: (
                grade_rank.get(r.grade, -1),
                max(r.probabilities.get("MORE", 0), r.probabilities.get("LESS", 0)),
            ),
            reverse=True,
        )
        selected.append(actionable[0])
    return selected


def _grade(action: NbaRecommendation, prob: float) -> str:
    if action is NbaRecommendation.PASS:
        return "PASS"
    if prob >= A_TIER_MIN_PROB:
        return "A"
    if prob >= 0.60:
        return "B"
    if prob >= 0.55:
        return "C"
    return "D"


def evaluate_nba_prop(
    envelope: EvidenceEnvelope,
    *,
    cutoff: PointInTimeCutoff | None = None,
    history: Sequence[PlayerGameStat] | None = None,
    min_sample: int = MIN_RESEARCH_SAMPLE,
) -> NbaPropDecision:
    game_id = str(envelope.map_context.get("game", {}).get("id") or envelope.fixture.event_id)
    if cutoff is None:
        cutoff = PointInTimeCutoff(
            game_id=game_id,
            game_start=envelope.fixture.start_time,
            as_of=envelope.fixture.start_time,
            recorded_at=envelope.captured_at,
        )
    cutoff = ensure_cutoff_recorded(cutoff, game_id=cutoff.game_id)

    evidence_gate = evidence_quality_gate(envelope)
    line_obj = next(iter(envelope.market_lines), None)
    reasons: list[str] = []

    if not evidence_gate.passed:
        reasons.append(f"evidence_quality:{evidence_gate.detail}")

    if line_obj is None:
        reasons.append("missing_market_line")
        prop = PropProbability(
            more=0.5,
            less=0.5,
            line=float("nan"),
            projection=float("nan"),
            sample_size=0,
            failure_paths=("missing_market_line",),
        )
        research_gate = NbaGateResult("research", False, "missing_market_line")
        cert = NbaGateResult("a_tier_certification", False, "blocked")
        return NbaPropDecision(
            action=NbaRecommendation.PASS,
            reasons=tuple(reasons),
            evidence_gate=evidence_gate,
            research_gate=research_gate,
            certification_gate=cert,
            probabilities={"MORE": 0.5, "LESS": 0.5, "PASS": 1.0},
            prop=prop,
            grade="PASS",
            cutoff=cutoff,
            market_notes=("no_line",),
            provenance=tuple(p.__dict__ for p in envelope.provenance),
        )

    hist = list(history) if history is not None else stats_from_envelope_context(
        envelope.map_context
    )
    # Drop any history not knowable before cutoff (defense in depth).
    hist = [
        h
        for h in hist
        if parse_iso(h.observed_at) < parse_iso(cutoff.as_of)
        and parse_iso(h.game_start) < parse_iso(cutoff.as_of)
    ]

    opponent_id = None
    game = envelope.map_context.get("game") or {}
    # Crude opponent inference unused unless present on stats.
    windows = research_bundle(
        hist,
        as_of=cutoff.as_of,
        player_id=str(line_obj.player_id),
        stat_name=str(line_obj.stat),
        opponent_team_id=opponent_id,
        season=game.get("season"),
    )
    prop = prop_probabilities(windows, line=float(line_obj.line), min_sample=min_sample)
    research_ok = prop.sample_size >= min_sample and not any(
        f.startswith("no_usable") for f in prop.failure_paths
    )
    research_gate = NbaGateResult(
        name="research",
        passed=research_ok,
        detail=(
            f"sample_size={prop.sample_size} failures={list(prop.failure_paths)}"
        ),
        value=float(prop.sample_size),
    )
    if not research_ok:
        reasons.append(f"research:{research_gate.detail}")

    snapshots = _snapshots_from_envelope(envelope)
    # Reject post-tip market rows.
    bad_markets = [
        s
        for s in snapshots
        if not market_snapshot_usable(captured_at=s.captured_at, game_start=cutoff.game_start)
    ]
    if bad_markets:
        reasons.append(f"rejected_post_tip_markets:{len(bad_markets)}")
    comparison = compare_to_market(prop, snapshots, game_start=cutoff.game_start)

    action = NbaRecommendation.PASS
    if evidence_gate.passed and research_ok:
        if prop.more >= prop.less and prop.more >= 0.55:
            action = NbaRecommendation.MORE
        elif prop.less > prop.more and prop.less >= 0.55:
            action = NbaRecommendation.LESS
        else:
            reasons.append("edge_below_threshold")
    else:
        reasons.append("PASS")

    chosen_prob = (
        prop.more
        if action is NbaRecommendation.MORE
        else prop.less
        if action is NbaRecommendation.LESS
        else 0.0
    )
    grade = _grade(action, chosen_prob)
    # Certification remains pending until walk-forward leakage tests pass in CI;
    # this gate records A-tier *criteria* but does not claim global certification.
    cert_ok = (
        grade == "A"
        and evidence_gate.passed
        and research_ok
        and action is not NbaRecommendation.PASS
        and comparison.deferred_to_market is False
    )
    cert = NbaGateResult(
        name="a_tier_certification",
        passed=cert_ok,
        detail=(
            "meets local A-tier criteria (global certification pending walk-forward suite)"
            if cert_ok
            else "not A-tier / certification pending"
        ),
        value=chosen_prob,
    )

    return NbaPropDecision(
        action=action,
        reasons=tuple(reasons) if action is NbaRecommendation.PASS else tuple(reasons),
        evidence_gate=evidence_gate,
        research_gate=research_gate,
        certification_gate=cert,
        probabilities={
            "MORE": prop.more,
            "LESS": prop.less,
            "PASS": 1.0 if action is NbaRecommendation.PASS else 0.0,
        },
        prop=prop,
        grade=grade,
        cutoff=cutoff,
        market_notes=comparison.notes,
        provenance=tuple(p.__dict__ for p in envelope.provenance),
    )
