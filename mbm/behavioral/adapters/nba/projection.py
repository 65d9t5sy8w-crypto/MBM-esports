"""Compare independent MBM projections against sportsbook lines.

Never automatically defers to the market. Market prices are evidence for
comparison and ROI measurement only.
"""

from __future__ import annotations

from typing import Sequence

from mbm.behavioral.adapters.nba.leakage import market_snapshot_usable
from mbm.behavioral.adapters.nba.props import american_to_implied_prob
from mbm.behavioral.adapters.nba.types import MarketComparison, MarketSnapshot, PropProbability


def select_pre_tip_snapshots(
    snapshots: Sequence[MarketSnapshot],
    *,
    game_start: str,
) -> list[MarketSnapshot]:
    return [
        s
        for s in snapshots
        if market_snapshot_usable(captured_at=s.captured_at, game_start=game_start)
    ]


def filter_snapshots_for_market(
    snapshots: Sequence[MarketSnapshot],
    *,
    game_id: str,
    player_id: str | None,
    prop_type: str,
) -> list[MarketSnapshot]:
    """Keep snapshots for the same game / player / prop type only."""
    out: list[MarketSnapshot] = []
    for s in snapshots:
        if str(s.game_id) != str(game_id):
            continue
        if str(s.prop_type) != str(prop_type):
            continue
        if player_id is not None and s.player_id is not None:
            if str(s.player_id) != str(player_id):
                continue
        elif player_id is not None and s.player_id is None:
            # Game totals / spreads have no player — exclude for player props.
            continue
        out.append(s)
    return out


def compare_to_market(
    prop: PropProbability,
    snapshots: Sequence[MarketSnapshot],
    *,
    game_start: str,
    game_id: str | None = None,
    player_id: str | None = None,
    prop_type: str | None = None,
) -> MarketComparison:
    scoped = list(snapshots)
    if game_id is not None and prop_type is not None:
        scoped = filter_snapshots_for_market(
            scoped, game_id=game_id, player_id=player_id, prop_type=prop_type
        )
    usable = select_pre_tip_snapshots(scoped, game_start=game_start)
    notes: list[str] = []
    if not usable:
        notes.append("no_pre_tip_market_snapshot")
        return MarketComparison(
            mbm_projection=prop.projection,
            market_line=prop.line,
            mbm_more_prob=prop.more,
            market_implied_more=None,
            edge_more=None,
            deferred_to_market=False,
            notes=tuple(notes),
        )

    # Prefer snapshot matching prop line; else latest pre-tip for same market.
    matched = [s for s in usable if abs(s.line - prop.line) < 1e-9]
    chosen = sorted(matched or list(usable), key=lambda s: s.captured_at)[-1]
    implied = american_to_implied_prob(chosen.more_odds)
    line_matches = abs(chosen.line - prop.line) < 1e-9
    edge = (prop.more - implied) if implied is not None and line_matches else None
    if not line_matches:
        notes.append("edge_unavailable_line_mismatch")
    notes.append(
        f"compared_to_vendor={chosen.vendor};source={chosen.source_identity};"
        f"raw_ref={chosen.raw_evidence_ref};captured_at={chosen.captured_at}"
    )
    notes.append("mbm_does_not_auto_defer_to_market")
    return MarketComparison(
        mbm_projection=prop.projection,
        market_line=float(chosen.line),
        mbm_more_prob=prop.more,
        market_implied_more=implied,
        edge_more=edge,
        deferred_to_market=False,
        notes=tuple(notes),
    )
