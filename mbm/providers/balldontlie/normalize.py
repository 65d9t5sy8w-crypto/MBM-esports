"""Normalize BallDontLie NBA bundles into EvidenceEnvelope (live or synthetic)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from mbm.intake.normalization.manual_panel import strip_secrets
from mbm.intake.types import (
    EvidenceEnvelope,
    EvidenceStatus,
    FixtureIdentity,
    IdentityStatus,
    MarketLine,
    MarketScope,
    PlayerIdentity,
    ProvenanceItem,
    SourceAttempt,
)

SOURCE_BALLDONTLIE = "balldontlie"
SOURCE_SYNTHETIC = "synthetic_test_fixture"
NBA_MARKET_SCOPE = MarketScope.FULL_GAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_list(payload: Any) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("data", "results", "items"):
            val = payload.get(key)
            if isinstance(val, list):
                return val
        if "id" in payload:
            return [payload]
    return []


def _team_label(team: Any) -> str:
    if not isinstance(team, dict):
        return ""
    return str(
        team.get("full_name")
        or team.get("name")
        or team.get("abbreviation")
        or (f"team:{team['id']}" if team.get("id") is not None else "")
    )


def _game_start(game: dict[str, Any], fallback: str) -> str:
    for key in ("datetime", "date"):
        val = game.get(key)
        if not val:
            continue
        text = str(val)
        if "T" in text:
            # Preserve existing offsets (including negative, e.g. -05:00).
            return (
                text
                if text.endswith("Z") or "+" in text[10:] or "-" in text[10:]
                else f"{text}Z"
            )
        # date-only → treat as tip-off unknown; use midnight UTC of that date
        return f"{text}T00:00:00Z"
    return fallback


def unavailable_envelope(
    reason: str,
    *,
    captured_at: str | None = None,
    attempts: list[SourceAttempt] | None = None,
    raw_ref: str | None = None,
    source: str = SOURCE_BALLDONTLIE,
) -> EvidenceEnvelope:
    captured = captured_at or _now_iso()
    ledger = list(attempts or [])
    ledger.append(SourceAttempt(source=source, outcome="unavailable", detail=reason))
    return EvidenceEnvelope(
        source=source,
        captured_at=captured,
        fixture=FixtureIdentity(
            event_id="balldontlie-unavailable",
            team_a="",
            team_b="",
            start_time=captured,
            format="nba_game",
            market_scope=NBA_MARKET_SCOPE,
        ),
        players=[],
        match_logs=[],
        map_context={"sport": "nba", "not_for_projection": source == SOURCE_SYNTHETIC},
        market_lines=[],
        evidence_status=EvidenceStatus.UNRESOLVED,
        identity_status=IdentityStatus.UNRESOLVED,
        provenance=[
            ProvenanceItem(name="balldontlie_unavailable_reason", source=source, value=reason),
            ProvenanceItem(name="pass_reasons", source=source, value=[reason]),
            ProvenanceItem(
                name="not_for_projection",
                source=source,
                value=source == SOURCE_SYNTHETIC,
            ),
        ],
        evidence_completeness={},
        source_attempts=ledger,
        raw_ref=raw_ref,
        target_player_id=None,
    )


def _extract_market_prices(odds_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prices: list[dict[str, Any]] = []
    for row in odds_rows:
        if not isinstance(row, dict):
            continue
        prices.append(
            {
                "source_identity": "balldontlie",
                "vendor": row.get("vendor"),
                "game_id": row.get("game_id"),
                "spread_home_value": row.get("spread_home_value"),
                "spread_home_odds": row.get("spread_home_odds"),
                "spread_away_value": row.get("spread_away_value"),
                "spread_away_odds": row.get("spread_away_odds"),
                "moneyline_home_odds": row.get("moneyline_home_odds"),
                "moneyline_away_odds": row.get("moneyline_away_odds"),
                "total_value": row.get("total_value"),
                "total_over_odds": row.get("total_over_odds"),
                "total_under_odds": row.get("total_under_odds"),
                "updated_at": row.get("updated_at"),
                "raw_evidence_ref": f"odds:{row.get('id')}",
            }
        )
    return prices


def _parse_iso_safe(ts: str) -> datetime | None:
    try:
        text = str(ts).strip().replace("Z", "+00:00")
        if "T" not in text:
            text = f"{text}T00:00:00+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _extract_prop_lines(
    props: list[dict[str, Any]],
    *,
    target_player_id: str | None,
    game_start: str | None = None,
    game_id: str | None = None,
) -> list[MarketLine]:
    """Build market lines; reject rows updated on/after tip-off when known.

    When ``game_id`` is set, only props for that game are accepted.
    """
    cutoff = _parse_iso_safe(game_start) if game_start else None
    lines: list[MarketLine] = []
    for row in props:
        if not isinstance(row, dict):
            continue
        if game_id is not None and str(row.get("game_id") or "") != str(game_id):
            continue
        pid = str(row.get("player_id") or "")
        if target_player_id and pid != str(target_player_id):
            continue
        updated = row.get("updated_at") or row.get("captured_at")
        if cutoff is not None:
            if not updated:
                continue
            obs = _parse_iso_safe(str(updated))
            if obs is None or obs >= cutoff:
                continue
        try:
            line_val = float(row.get("line_value"))
        except (TypeError, ValueError):
            continue
        stat = str(row.get("prop_type") or "unknown")
        lines.append(
            MarketLine(
                player_id=pid or "unknown",
                stat=stat,
                line=line_val,
                market_scope=NBA_MARKET_SCOPE,
            )
        )
    return lines


def normalize_balldontlie_bundle(
    bundle: dict[str, Any],
    *,
    captured_at: str | None = None,
    raw_ref: str | None = None,
    target_player_id: str | None = None,
    line: float | None = None,
    prop_stat: str = "points",
    force_source: str | None = None,
    not_for_projection: bool | None = None,
) -> EvidenceEnvelope:
    """Normalize a BallDontLie NBA bundle (live or synthetic).

    Expected optional keys: teams, players, games, stats, advanced_stats,
    injuries, lineups, projected_lineups, odds, player_props, http_meta.
    """
    clean = strip_secrets(bundle)
    source = force_source or str(clean.get("source") or SOURCE_BALLDONTLIE)
    if source not in {SOURCE_BALLDONTLIE, SOURCE_SYNTHETIC}:
        raise ValueError(f"unsupported BallDontLie bundle source: {source}")
    synthetic = source == SOURCE_SYNTHETIC
    if not_for_projection is None:
        not_for_projection = bool(clean.get("not_for_projection", synthetic))
    if synthetic and not not_for_projection:
        raise ValueError("synthetic_test_fixture must set not_for_projection=true")

    captured = captured_at or (
        str(clean["captured_at"])
        if clean.get("captured_at")
        else (_now_iso() if not synthetic else "1970-01-01T00:00:00Z")
    )

    attempts: list[SourceAttempt] = []
    for meta in clean.get("http_meta") or []:
        if not isinstance(meta, dict):
            continue
        endpoint = str(meta.get("endpoint") or meta.get("path") or source)
        reason = meta.get("unavailable_reason")
        tag = "synthetic" if meta.get("synthetic") or synthetic else source
        if reason:
            attempts.append(
                SourceAttempt(source=tag, outcome="unavailable", detail=f"{endpoint}: {reason}")
            )
        else:
            attempts.append(
                SourceAttempt(
                    source=tag,
                    outcome="accepted",
                    detail=(
                        f"{endpoint} HTTP {meta.get('status')} "
                        f"enabled={meta.get('enabled')} "
                        f"content_type={meta.get('content_type')}"
                    ),
                )
            )

    games = [g for g in _as_list(clean.get("games")) if isinstance(g, dict) and g.get("id")]
    if not games:
        reason = "BallDontLie unavailable: no game objects in bundle"
        if any(a.outcome == "unavailable" for a in attempts):
            reason = next(a.detail for a in attempts if a.outcome == "unavailable")
        return unavailable_envelope(
            reason,
            captured_at=captured,
            attempts=attempts,
            raw_ref=raw_ref,
            source=source,
        )

    game = games[0]
    event_id = str(game["id"])
    team_a = _team_label(game.get("home_team"))
    team_b = _team_label(game.get("visitor_team"))
    start = _game_start(game, captured)

    players_raw = [p for p in _as_list(clean.get("players")) if isinstance(p, dict)]
    players: list[PlayerIdentity] = []
    for p in players_raw:
        pid = str(p.get("id") or "")
        name = f"{p.get('first_name', '')} {p.get('last_name', '')}".strip() or pid
        team = _team_label(p.get("team")) if isinstance(p.get("team"), dict) else ""
        players.append(PlayerIdentity(player_id=pid, name=name, team=team))

    odds_rows = [
        r
        for r in _as_list(clean.get("odds"))
        if isinstance(r, dict) and (r.get("game_id") is None or str(r.get("game_id")) == event_id)
    ]
    prop_rows = [
        r
        for r in _as_list(clean.get("player_props"))
        if isinstance(r, dict) and str(r.get("game_id") or "") == event_id
    ]
    sportsbook_prices = _extract_market_prices(odds_rows)
    market_lines = _extract_prop_lines(
        prop_rows,
        target_player_id=target_player_id,
        game_start=start,
        game_id=event_id,
    )

    # Mason-attached line for gate tests — never fabricate a resolved PlayerIdentity.
    if target_player_id is not None and line is not None and not any(
        m.player_id == str(target_player_id) and m.stat == prop_stat for m in market_lines
    ):
        market_lines.append(
            MarketLine(
                player_id=str(target_player_id),
                stat=prop_stat,
                line=float(line),
                market_scope=NBA_MARKET_SCOPE,
            )
        )

    injuries = [r for r in _as_list(clean.get("injuries")) if isinstance(r, dict)]
    advanced = [r for r in _as_list(clean.get("advanced_stats")) if isinstance(r, dict)]
    stats = [r for r in _as_list(clean.get("stats")) if isinstance(r, dict)]
    lineups = [r for r in _as_list(clean.get("lineups")) if isinstance(r, dict)]
    projected = [r for r in _as_list(clean.get("projected_lineups")) if isinstance(r, dict)]

    map_context: dict[str, Any] = {
        "sport": "nba",
        "provider": source,
        "api": "balldontlie",
        "openapi_ref": "vendor/balldontlie/nba.yml",
        "game": {
            "id": game.get("id"),
            "date": game.get("date"),
            "datetime": game.get("datetime"),
            "status": game.get("status"),
            "status_state": game.get("status_state"),
            "season": game.get("season"),
            "home_team_score": game.get("home_team_score"),
            "visitor_team_score": game.get("visitor_team_score"),
        },
        "sportsbook_prices": sportsbook_prices,
        "player_props_raw_count": len(prop_rows),
        "stats_count": len(stats),
        "advanced_stats_count": len(advanced),
        "injuries_count": len(injuries),
        "lineups_count": len(lineups),
        "projected_lineups_count": len(projected),
        # Paid payloads may be present only via synthetic fixtures.
        "stats": stats,
        "advanced_stats": advanced,
        "injuries": injuries,
        "lineups": lineups,
        "projected_lineups": projected,
        "player_props": prop_rows,
        "not_for_projection": bool(not_for_projection),
        "paid_endpoints_live": False,
    }

    provenance = [
        ProvenanceItem(name="source", source=source, value=source),
        ProvenanceItem(
            name="captured_at",
            source=source,
            value=None if synthetic else captured,
        ),
        ProvenanceItem(name="not_for_projection", source=source, value=bool(not_for_projection)),
        ProvenanceItem(name="market_scope", source=source, value=NBA_MARKET_SCOPE.value),
        ProvenanceItem(name="event_id", source=source, value=event_id),
        ProvenanceItem(
            name="sportsbook_price_count", source=source, value=len(sportsbook_prices)
        ),
        ProvenanceItem(
            name="raw_evidence_ref",
            source=source,
            value=raw_ref,
        ),
    ]

    attempts.append(
        SourceAttempt(source=source, outcome="normalized", detail=f"event_id={event_id}")
    )

    status = EvidenceStatus.INCOMPLETE if synthetic or not_for_projection else EvidenceStatus.VERIFIED
    if not team_a or not team_b:
        status = EvidenceStatus.INCOMPLETE

    prefix = "synthetic" if synthetic else "balldontlie"
    return EvidenceEnvelope(
        source=source,
        captured_at=captured,
        fixture=FixtureIdentity(
            event_id=f"{prefix}-{event_id}",
            team_a=team_a,
            team_b=team_b,
            start_time=start,
            format="nba_game",
            market_scope=NBA_MARKET_SCOPE,
        ),
        players=players,
        match_logs=[],
        map_context=map_context,
        market_lines=market_lines,
        evidence_status=status,
        identity_status=(
            IdentityStatus.RESOLVED
            if team_a and team_b and (target_player_id is None or any(p.player_id == str(target_player_id) for p in players))
            else IdentityStatus.UNRESOLVED
        ),
        provenance=provenance,
        evidence_completeness={
            "games": True,
            "market_board": bool(sportsbook_prices) or bool(market_lines),
            "player_stats": bool(stats),
            "injuries": bool(injuries),
        },
        source_attempts=attempts,
        raw_ref=raw_ref,
        target_player_id=str(target_player_id) if target_player_id else None,
    )
