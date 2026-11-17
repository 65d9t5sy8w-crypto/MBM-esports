"""NBA player research windows: last-5, last-10, season, opponent-specific.

All windows respect a point-in-time ``as_of`` cutoff (exclusive). Sample sizes
are always returned. Post-game stats and future injuries are excluded.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from mbm.behavioral.adapters.nba.leakage import parse_iso
from mbm.behavioral.adapters.nba.types import AnalysisWindow, WindowSummary


@dataclass(frozen=True)
class PlayerGameStat:
    game_id: str
    player_id: str
    game_start: str
    opponent_team_id: str
    season: int
    stat_name: str
    stat_value: float
    # When the box score / stat became knowable (must be >= game end; never before tip).
    observed_at: str


def _mean(vals: Sequence[float]) -> float | None:
    if not vals:
        return None
    return sum(vals) / len(vals)


def eligible_history(
    history: Sequence[PlayerGameStat],
    *,
    as_of: str,
    player_id: str,
    stat_name: str,
) -> list[PlayerGameStat]:
    """History usable at ``as_of``: game must have started AND stats observed before cutoff.

    A game whose tip-off is before ``as_of`` but whose stats were observed after
    ``as_of`` is excluded (no look-ahead on settlement-driven box scores).
    """
    cutoff = parse_iso(as_of)
    out: list[PlayerGameStat] = []
    for row in history:
        if str(row.player_id) != str(player_id):
            continue
        if row.stat_name != stat_name:
            continue
        if parse_iso(row.game_start) >= cutoff:
            continue
        if parse_iso(row.observed_at) >= cutoff:
            continue
        out.append(row)
    out.sort(key=lambda r: parse_iso(r.game_start))
    return out


def summarize_window(
    history: Sequence[PlayerGameStat],
    *,
    window: AnalysisWindow,
    as_of: str,
    player_id: str,
    stat_name: str,
    opponent_team_id: str | None = None,
    season: int | None = None,
) -> WindowSummary:
    rows = eligible_history(
        history, as_of=as_of, player_id=player_id, stat_name=stat_name
    )
    notes: list[str] = []

    if window is AnalysisWindow.LAST_5:
        selected = rows[-5:]
    elif window is AnalysisWindow.LAST_10:
        selected = rows[-10:]
    elif window is AnalysisWindow.SEASON:
        if season is None:
            notes.append("season window requested without season filter; using all eligible")
            selected = rows
        else:
            selected = [r for r in rows if r.season == season]
    elif window is AnalysisWindow.OPPONENT:
        if not opponent_team_id:
            return WindowSummary(
                window=window,
                sample_size=0,
                mean=None,
                values=(),
                as_of=as_of,
                opponent_team_id=None,
                notes=("opponent window requires opponent_team_id",),
            )
        selected = [r for r in rows if str(r.opponent_team_id) == str(opponent_team_id)]
    else:
        raise ValueError(f"unsupported window {window}")

    values = tuple(float(r.stat_value) for r in selected)
    return WindowSummary(
        window=window,
        sample_size=len(values),
        mean=_mean(values),
        values=values,
        as_of=as_of,
        opponent_team_id=opponent_team_id,
        notes=tuple(notes),
    )


def research_bundle(
    history: Sequence[PlayerGameStat],
    *,
    as_of: str,
    player_id: str,
    stat_name: str,
    opponent_team_id: str | None = None,
    season: int | None = None,
) -> dict[str, WindowSummary]:
    return {
        w.value: summarize_window(
            history,
            window=w,
            as_of=as_of,
            player_id=player_id,
            stat_name=stat_name,
            opponent_team_id=opponent_team_id,
            season=season,
        )
        for w in (
            AnalysisWindow.LAST_5,
            AnalysisWindow.LAST_10,
            AnalysisWindow.SEASON,
            AnalysisWindow.OPPONENT,
        )
    }


def stats_from_envelope_context(map_context: dict[str, Any]) -> list[PlayerGameStat]:
    """Best-effort parse of synthetic/live stats rows stored on the envelope."""
    out: list[PlayerGameStat] = []
    for row in map_context.get("stats") or []:
        if not isinstance(row, dict):
            continue
        game = row.get("game") if isinstance(row.get("game"), dict) else {}
        player = row.get("player") if isinstance(row.get("player"), dict) else {}
        team = row.get("team") if isinstance(row.get("team"), dict) else {}
        opp = row.get("opponent_team_id") or row.get("opponent_team", {})
        if isinstance(opp, dict):
            opp_id = str(opp.get("id") or "")
        else:
            opp_id = str(opp or "")
        game_id = str(game.get("id") or row.get("game_id") or "")
        game_start = str(
            game.get("datetime")
            or row.get("game_start")
            or game.get("date")
            or row.get("observed_at")
            or ""
        )
        observed = str(row.get("observed_at") or game_start)
        player_id = str(player.get("id") or row.get("player_id") or "")
        season = int(game.get("season") or row.get("season") or 0)
        for stat_name in ("pts", "reb", "ast", "stl", "blk", "fg3m"):
            if stat_name in row and row[stat_name] is not None:
                try:
                    val = float(row[stat_name])
                except (TypeError, ValueError):
                    continue
                # Normalize pts→points for prop alignment when present as pts.
                prop_stat = {
                    "pts": "points",
                    "reb": "rebounds",
                    "ast": "assists",
                    "fg3m": "threes",
                    "stl": "steals",
                    "blk": "blocks",
                }.get(stat_name, stat_name)
                out.append(
                    PlayerGameStat(
                        game_id=game_id,
                        player_id=player_id,
                        game_start=game_start,
                        opponent_team_id=opp_id or str(team.get("id") or ""),
                        season=season,
                        stat_name=prop_stat,
                        stat_value=val,
                        observed_at=observed,
                    )
                )
    return out
