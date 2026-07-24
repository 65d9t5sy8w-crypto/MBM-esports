"""Normalize BO3-shaped bundles into EvidenceEnvelope (live or synthetic)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from mbm.intake.normalization.manual_panel import strip_secrets
from mbm.intake.types import (
    DEFAULT_MARKET_SCOPE,
    EvidenceEnvelope,
    EvidenceStatus,
    FixtureIdentity,
    IdentityStatus,
    MarketLine,
    MarketScope,
    MatchLogSample,
    PlayerIdentity,
    ProvenanceItem,
    SourceAttempt,
)

SOURCE_BO3 = "bo3.gg"
SOURCE_SYNTHETIC = "synthetic_test_fixture"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _results(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("results", "data", "matches", "items"):
            val = payload.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
        # single match object
        if "id" in payload or "slug" in payload:
            return [payload]
    return []


def _team_name(team: Any) -> str:
    if isinstance(team, dict):
        return str(team.get("name") or team.get("title") or team.get("slug") or "")
    return str(team or "")


def _extract_teams(match: dict[str, Any]) -> tuple[str, str]:
    teams = match.get("teams") or match.get("team") or []
    if isinstance(teams, list) and len(teams) >= 2:
        return _team_name(teams[0]), _team_name(teams[1])
    team_a = match.get("team1") or match.get("team_a") or match.get("home_team")
    team_b = match.get("team2") or match.get("team_b") or match.get("away_team")
    return _team_name(team_a), _team_name(team_b)


def _bo3_format(match: dict[str, Any]) -> str:
    bo = match.get("best_of") or match.get("bo") or match.get("format")
    if bo is None:
        return "bo3"
    text = str(bo).lower()
    if text.startswith("bo"):
        return text
    if text.isdigit():
        return f"bo{text}"
    return text


def _players_from_match(match: dict[str, Any]) -> list[PlayerIdentity]:
    players: list[PlayerIdentity] = []
    for team in match.get("teams") or []:
        if not isinstance(team, dict):
            continue
        team_name = _team_name(team)
        for p in team.get("players") or team.get("lineup") or []:
            if not isinstance(p, dict):
                continue
            pid = str(p.get("id") or p.get("player_id") or "")
            if not pid:
                continue
            players.append(
                PlayerIdentity(
                    player_id=pid,
                    name=str(p.get("nickname") or p.get("name") or pid),
                    team=team_name,
                )
            )
    return players


def _logs_from_history(history: Any, *, scope: MarketScope) -> list[MatchLogSample]:
    logs: list[MatchLogSample] = []
    for row in _results(history):
        # BO3 match widgets rarely include per-map HS; leave zeros → completeness PASS.
        stats = row.get("player_stats") or row.get("stats") or {}
        if not isinstance(stats, dict):
            stats = {}
        logs.append(
            MatchLogSample(
                match_id=str(row.get("id") or row.get("slug") or f"bo3-{len(logs)}"),
                market_scope=scope,
                kills=float(stats.get("kills") or stats.get("k") or 0),
                deaths=float(stats.get("deaths") or stats.get("d") or 0),
                assists=float(stats.get("assists") or stats.get("a") or 0),
                headshots=float(stats.get("headshots") or stats.get("hs") or 0),
                opening_kills=float(stats.get("opening_kills") or 0),
                opening_deaths=float(stats.get("opening_deaths") or 0),
                rounds_played=float(stats.get("rounds") or stats.get("rounds_played") or 0),
                ct_rounds=float(stats.get("ct_rounds") or 0),
                t_rounds=float(stats.get("t_rounds") or 0),
                economy=(),
            )
        )
    return logs


def unavailable_envelope(
    reason: str,
    *,
    captured_at: str | None = None,
    attempts: list[SourceAttempt] | None = None,
    raw_ref: str | None = None,
    source: str = SOURCE_BO3,
) -> EvidenceEnvelope:
    """Canonical envelope when BO3 cannot supply usable JSON."""
    captured = captured_at or _now_iso()
    ledger = list(attempts or [])
    ledger.append(SourceAttempt(source=source, outcome="unavailable", detail=reason))
    return EvidenceEnvelope(
        source=source,
        captured_at=captured,
        fixture=FixtureIdentity(
            event_id="bo3-unavailable",
            team_a="",
            team_b="",
            start_time=captured,
            format="bo3",
            market_scope=DEFAULT_MARKET_SCOPE,
        ),
        players=[],
        match_logs=[],
        map_context={"not_for_projection": source == SOURCE_SYNTHETIC},
        market_lines=[],
        evidence_status=EvidenceStatus.UNRESOLVED,
        identity_status=IdentityStatus.UNRESOLVED,
        provenance=[
            ProvenanceItem(name="bo3_unavailable_reason", source=source, value=reason),
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


def normalize_bo3_bundle(
    bundle: dict[str, Any],
    *,
    captured_at: str | None = None,
    raw_ref: str | None = None,
    target_player_id: str | None = None,
    line: float | None = None,
    force_source: str | None = None,
    not_for_projection: bool | None = None,
    captured_at_display: str | None = ...,  # type: ignore[assignment]
) -> EvidenceEnvelope:
    """Normalize a BO3-shaped bundle (live provider or synthetic test shape).

    Expected keys (any may be missing → explicit PASS reasons via attempts):
      upcoming, live, finished, match_detail, player_history, team_search,
      http_meta (list of {endpoint, status, content_type, unavailable_reason})

    Hand-authored fixtures must pass force_source=synthetic_test_fixture and
    not_for_projection=True. Only byte-for-byte BO3 responses may use source=bo3.gg.
    """
    clean = strip_secrets(bundle)
    source = force_source or str(clean.get("source") or SOURCE_BO3)
    if source not in {SOURCE_BO3, SOURCE_SYNTHETIC}:
        raise ValueError(f"unsupported BO3 bundle source: {source}")
    synthetic = source == SOURCE_SYNTHETIC
    if not_for_projection is None:
        not_for_projection = bool(clean.get("not_for_projection", synthetic))
    if synthetic and not not_for_projection:
        raise ValueError("synthetic_test_fixture must set not_for_projection=true")

    if captured_at_display is ...:
        # Default: use provided captured_at; synthetic may keep null in provenance.
        display_captured = clean.get("captured_at") if "captured_at" in clean else captured_at
    else:
        display_captured = captured_at_display

    captured = captured_at or (
        str(clean["captured_at"])
        if clean.get("captured_at")
        else (_now_iso() if not synthetic else "1970-01-01T00:00:00Z")
    )
    attempts: list[SourceAttempt] = []
    for meta in clean.get("http_meta") or []:
        if not isinstance(meta, dict):
            continue
        reason = meta.get("unavailable_reason")
        endpoint = str(meta.get("endpoint") or meta.get("url") or source)
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
                        f"content_type={meta.get('content_type')}"
                    ),
                )
            )

    # Prefer detail, else first upcoming/live/finished result.
    detail = clean.get("match_detail")
    matches = _results(detail)
    if not matches:
        for key in ("upcoming", "live", "finished"):
            matches = _results(clean.get(key))
            if matches:
                attempts.append(
                    SourceAttempt(
                        source=source,
                        outcome="accepted",
                        detail=f"selected match from {key} listing",
                    )
                )
                break

    if not matches:
        reason = "BO3 unavailable: no match objects in upcoming/live/finished/detail"
        if any(a.outcome == "unavailable" for a in attempts):
            reason = next(a.detail for a in attempts if a.outcome == "unavailable")
        return unavailable_envelope(
            reason,
            captured_at=captured,
            attempts=attempts,
            raw_ref=raw_ref,
            source=source,
        )

    match = matches[0]
    team_a, team_b = _extract_teams(match)
    event_id = str(match.get("id") or match.get("slug") or "unknown")
    start = str(match.get("start_date") or match.get("start_time") or captured)
    players = _players_from_match(match)
    logs = _logs_from_history(clean.get("player_history"), scope=DEFAULT_MARKET_SCOPE)

    target = target_player_id or (players[0].player_id if players else None)
    market_lines: list[MarketLine] = []
    if target is not None and line is not None:
        market_lines.append(
            MarketLine(
                player_id=str(target),
                stat="headshots",
                line=float(line),
                market_scope=MarketScope.MAPS_1_2,
            )
        )

    map_context: dict[str, Any] = {
        "tournament": (match.get("tournament") or {}),
        "games": match.get("games") or match.get("maps") or [],
        "status": match.get("status"),
        "provider": source,
        "not_for_projection": bool(not_for_projection),
    }

    provenance = [
        ProvenanceItem(name="source", source=source, value=source),
        ProvenanceItem(
            name="captured_at",
            source=source,
            value=display_captured if display_captured is not None else (None if synthetic else captured),
        ),
        ProvenanceItem(name="not_for_projection", source=source, value=bool(not_for_projection)),
        ProvenanceItem(name="market_scope", source=source, value=DEFAULT_MARKET_SCOPE.value),
        ProvenanceItem(name="event_id", source=source, value=event_id),
    ]

    attempts.append(
        SourceAttempt(source=source, outcome="normalized", detail=f"event_id={event_id}")
    )

    status = EvidenceStatus.INCOMPLETE if synthetic or not_for_projection else EvidenceStatus.VERIFIED
    if not players or not team_a or not team_b:
        status = EvidenceStatus.INCOMPLETE

    prefix = "synthetic" if synthetic else "bo3"
    return EvidenceEnvelope(
        source=source,
        captured_at=captured,
        fixture=FixtureIdentity(
            event_id=f"{prefix}-{event_id}",
            team_a=team_a,
            team_b=team_b,
            start_time=start,
            format=_bo3_format(match),
            market_scope=DEFAULT_MARKET_SCOPE,
        ),
        players=players,
        match_logs=logs,
        map_context=map_context,
        market_lines=market_lines,
        evidence_status=status,
        identity_status=IdentityStatus.UNRESOLVED,
        provenance=provenance,
        source_attempts=attempts,
        raw_ref=raw_ref,
        target_player_id=str(target) if target else None,
    )
