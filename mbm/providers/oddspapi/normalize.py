"""Normalize OddsPapi-shaped bundles into EvidenceEnvelope (live or synthetic)."""

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
    PlayerIdentity,
    ProvenanceItem,
    SourceAttempt,
)

SOURCE_ODDSPAPI = "oddspapi"
SOURCE_SYNTHETIC = "synthetic_test_fixture"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _epoch_to_iso(value: Any, fallback: str) -> str:
    if value is None or value == "":
        return fallback
    if isinstance(value, str) and not value.isdigit():
        return value
    try:
        ts = int(value)
        # OddsPapi startTime is epoch seconds; changedAt may be ms.
        if ts > 10_000_000_000:
            ts = ts // 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError, OverflowError):
        return fallback


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("results", "data", "fixtures", "items"):
            val = payload.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
        if "fixtureId" in payload or "id" in payload:
            return [payload]
    return []


def _participant_names(fixture: dict[str, Any]) -> tuple[str, str]:
    parts = fixture.get("participants") or {}
    if isinstance(parts, dict):
        a = str(
            parts.get("participant1Name")
            or parts.get("homeName")
            or parts.get("team_a")
            or ""
        )
        b = str(
            parts.get("participant2Name")
            or parts.get("awayName")
            or parts.get("team_b")
            or ""
        )
        if a or b:
            return a, b
    if isinstance(parts, list) and len(parts) >= 2:
        def _name(row: Any) -> str:
            if isinstance(row, dict):
                return str(row.get("name") or row.get("participantName") or "")
            return str(row or "")

        return _name(parts[0]), _name(parts[1])
    return (
        str(fixture.get("team_a") or fixture.get("home") or ""),
        str(fixture.get("team_b") or fixture.get("away") or ""),
    )


def _players_from_odds_and_roster(
    fixture: dict[str, Any],
    odds_payload: Any,
    players_payload: Any,
) -> list[PlayerIdentity]:
    by_id: dict[str, PlayerIdentity] = {}
    team_a, team_b = _participant_names(fixture)
    parts = fixture.get("participants") if isinstance(fixture.get("participants"), dict) else {}
    p1 = str((parts or {}).get("participant1Id") or "")
    p2 = str((parts or {}).get("participant2Id") or "")

    for row in _as_list(players_payload):
        pid = str(row.get("playerId") or row.get("id") or "")
        if not pid:
            continue
        team = team_a
        part = str(row.get("participantId") or "")
        if part and part == p2:
            team = team_b
        elif part and part == p1:
            team = team_a
        by_id[pid] = PlayerIdentity(
            player_id=pid,
            name=str(row.get("playerName") or row.get("name") or pid),
            team=team,
        )

    # Player props on the odds board also introduce player ids.
    if isinstance(odds_payload, dict):
        odds_root = odds_payload.get("odds") if isinstance(odds_payload.get("odds"), dict) else odds_payload
        if isinstance(odds_root, dict):
            for book_map in odds_root.values():
                if not isinstance(book_map, dict):
                    continue
                for outcome in book_map.values():
                    if not isinstance(outcome, dict):
                        continue
                    pid_raw = outcome.get("playerId")
                    if pid_raw in (None, 0, "0", ""):
                        continue
                    pid = str(pid_raw)
                    if pid not in by_id:
                        by_id[pid] = PlayerIdentity(
                            player_id=pid,
                            name=str(outcome.get("playerName") or pid),
                            team="",
                        )
    return list(by_id.values())


def _looks_like_headshots(market_name: str, outcome: dict[str, Any]) -> bool:
    blob = " ".join(
        str(x)
        for x in (
            market_name,
            outcome.get("marketName"),
            outcome.get("marketNameShort"),
            outcome.get("bookmakerMarketId"),
            outcome.get("stat"),
        )
        if x
    ).lower()
    return "headshot" in blob or blob.strip() == "hs"


def _market_lines_from_odds(
    odds_payload: Any,
    *,
    target_player_id: str | None,
    line: float | None,
    markets_index: dict[str, dict[str, Any]] | None = None,
) -> list[MarketLine]:
    """Extract Maps 1–2 headshots lines from player-prop odds when present."""
    lines: list[MarketLine] = []
    seen: set[tuple[str, float]] = set()
    markets_index = markets_index or {}

    if target_player_id is not None and line is not None:
        key = (str(target_player_id), float(line))
        seen.add(key)
        lines.append(
            MarketLine(
                player_id=str(target_player_id),
                stat="headshots",
                line=float(line),
                market_scope=MarketScope.MAPS_1_2,
            )
        )

    if not isinstance(odds_payload, dict):
        return lines

    odds_root = odds_payload.get("odds") if isinstance(odds_payload.get("odds"), dict) else None
    if odds_root is None and any(
        isinstance(v, dict) and ("price" in next(iter(v.values()), {}) if v else False)
        for v in odds_payload.values()
        if isinstance(v, dict)
    ):
        odds_root = odds_payload
    if not isinstance(odds_root, dict):
        return lines

    for book_map in odds_root.values():
        if not isinstance(book_map, dict):
            continue
        for outcome in book_map.values():
            if not isinstance(outcome, dict):
                continue
            pid_raw = outcome.get("playerId")
            if pid_raw in (None, 0, "0", ""):
                continue
            market_id = str(outcome.get("marketId") or "")
            market_meta = markets_index.get(market_id, {})
            market_name = str(market_meta.get("marketName") or outcome.get("marketName") or "")
            if not _looks_like_headshots(market_name, outcome):
                continue
            handicap = outcome.get("handicap")
            if handicap is None:
                handicap = market_meta.get("handicap")
            if handicap is None:
                continue
            try:
                line_val = float(handicap)
            except (TypeError, ValueError):
                continue
            pid = str(pid_raw)
            key = (pid, line_val)
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                MarketLine(
                    player_id=pid,
                    stat="headshots",
                    line=line_val,
                    market_scope=MarketScope.MAPS_1_2,
                )
            )
    return lines


def _markets_index(markets_payload: Any) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for row in _as_list(markets_payload):
        mid = str(row.get("marketId") or row.get("id") or "")
        if mid:
            index[mid] = row
    return index


def unavailable_envelope(
    reason: str,
    *,
    captured_at: str | None = None,
    attempts: list[SourceAttempt] | None = None,
    raw_ref: str | None = None,
    source: str = SOURCE_ODDSPAPI,
) -> EvidenceEnvelope:
    """Canonical envelope when OddsPapi cannot supply usable JSON."""
    captured = captured_at or _now_iso()
    ledger = list(attempts or [])
    ledger.append(SourceAttempt(source=source, outcome="unavailable", detail=reason))
    return EvidenceEnvelope(
        source=source,
        captured_at=captured,
        fixture=FixtureIdentity(
            event_id="oddspapi-unavailable",
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
            ProvenanceItem(name="oddspapi_unavailable_reason", source=source, value=reason),
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


def normalize_oddspapi_bundle(
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
    """Normalize an OddsPapi-shaped bundle (live provider or synthetic test shape).

    Expected keys (any may be missing → explicit PASS reasons via attempts):
      sports, tournaments, fixtures, fixture_odds, participants, players, markets,
      http_meta (list of {endpoint, status, content_type, unavailable_reason})

    Hand-authored fixtures must pass force_source=synthetic_test_fixture and
    not_for_projection=True. Only byte-for-byte OddsPapi responses may use
    source=oddspapi.
    """
    clean = strip_secrets(bundle)
    source = force_source or str(clean.get("source") or SOURCE_ODDSPAPI)
    if source not in {SOURCE_ODDSPAPI, SOURCE_SYNTHETIC}:
        raise ValueError(f"unsupported OddsPapi bundle source: {source}")
    synthetic = source == SOURCE_SYNTHETIC
    if not_for_projection is None:
        not_for_projection = bool(clean.get("not_for_projection", synthetic))
    if synthetic and not not_for_projection:
        raise ValueError("synthetic_test_fixture must set not_for_projection=true")

    if captured_at_display is ...:
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

    odds = clean.get("fixture_odds")
    fixtures = _as_list(clean.get("fixtures"))
    fixture: dict[str, Any] | None = None
    if isinstance(odds, dict) and odds.get("fixtureId"):
        fixture = odds
        attempts.append(
            SourceAttempt(source=source, outcome="accepted", detail="selected fixture from fixture_odds")
        )
    elif fixtures:
        fixture = fixtures[0]
        attempts.append(
            SourceAttempt(source=source, outcome="accepted", detail="selected fixture from fixtures listing")
        )

    if fixture is None:
        reason = "OddsPapi unavailable: no fixture objects in fixtures/fixture_odds"
        if any(a.outcome == "unavailable" for a in attempts):
            reason = next(a.detail for a in attempts if a.outcome == "unavailable")
        return unavailable_envelope(
            reason,
            captured_at=captured,
            attempts=attempts,
            raw_ref=raw_ref,
            source=source,
        )

    team_a, team_b = _participant_names(fixture)
    event_id = str(fixture.get("fixtureId") or fixture.get("id") or "unknown")
    start = _epoch_to_iso(fixture.get("startTime") or fixture.get("start_time"), captured)
    players = _players_from_odds_and_roster(fixture, odds, clean.get("players"))
    market_lines = _market_lines_from_odds(
        odds if isinstance(odds, dict) else {},
        target_player_id=target_player_id,
        line=line,
        markets_index=_markets_index(clean.get("markets")),
    )

    target = target_player_id or (market_lines[0].player_id if market_lines else None)
    if target is None and players:
        target = players[0].player_id

    tournament = fixture.get("tournament") if isinstance(fixture.get("tournament"), dict) else {}
    map_context: dict[str, Any] = {
        "tournament": tournament,
        "sport": fixture.get("sport") or {"sportId": 17, "sportName": "ESport Counter-Strike"},
        "status": fixture.get("status"),
        "provider": source,
        "bookmakers": (odds.get("bookmakers") if isinstance(odds, dict) else None),
        "not_for_projection": bool(not_for_projection),
        # OddsPapi supplies market board, not CS2 match logs — completeness stays incomplete.
        "match_logs_source": "absent_from_oddspapi",
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
        ProvenanceItem(name="sport_id", source=source, value=17),
    ]

    attempts.append(
        SourceAttempt(source=source, outcome="normalized", detail=f"event_id={event_id}")
    )

    status = EvidenceStatus.INCOMPLETE if synthetic or not_for_projection else EvidenceStatus.VERIFIED
    if not team_a or not team_b:
        status = EvidenceStatus.INCOMPLETE
    # Odds-only boards cannot satisfy match-log completeness for Headshots gates.
    if not market_lines:
        status = EvidenceStatus.INCOMPLETE

    prefix = "synthetic" if synthetic else "oddspapi"
    return EvidenceEnvelope(
        source=source,
        captured_at=captured,
        fixture=FixtureIdentity(
            event_id=f"{prefix}-{event_id}",
            team_a=team_a,
            team_b=team_b,
            start_time=start,
            format="bo3",
            market_scope=DEFAULT_MARKET_SCOPE,
        ),
        players=players,
        match_logs=[],
        map_context=map_context,
        market_lines=market_lines,
        evidence_status=status,
        identity_status=IdentityStatus.UNRESOLVED,
        provenance=provenance,
        evidence_completeness={"match_logs": False, "market_board": bool(market_lines)},
        source_attempts=attempts,
        raw_ref=raw_ref,
        target_player_id=str(target) if target else None,
    )
