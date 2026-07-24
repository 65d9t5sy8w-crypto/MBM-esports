"""Normalize OddsPapi v4 bundles into EvidenceEnvelope (live or synthetic).

Ingests tournament/event/market-price evidence from verified v4 endpoints only.
Does not claim headshot (or other player-prop) availability unless an authentic
redacted v4 fixture demonstrates those fields.
"""

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
from mbm.providers.oddspapi.client import (
    SPORT_ID_CS2,
    SPORT_ID_LOL,
    SPORT_ID_VALORANT,
    VERIFIED_ESPORTS_SPORT_IDS,
)

SOURCE_ODDSPAPI = "oddspapi"
SOURCE_SYNTHETIC = "synthetic_test_fixture"

SPORT_LABELS = {
    SPORT_ID_CS2: "ESport Counter-Strike",
    SPORT_ID_LOL: "ESport League of Legends",
    SPORT_ID_VALORANT: "ESport Valorant",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_list(payload: Any) -> list[Any]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("results", "data", "fixtures", "items", "odds"):
            val = payload.get(key)
            if isinstance(val, list):
                return val
        if "fixtureId" in payload:
            return [payload]
    return []


def _start_time_iso(value: Any, fallback: str) -> str:
    if value is None or value == "":
        return fallback
    if isinstance(value, str) and not str(value).isdigit():
        return str(value)
    try:
        ts = int(value)
        if ts > 10_000_000_000:
            ts = ts // 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError, OverflowError):
        return str(value) if value else fallback


def _team_labels(fixture: dict[str, Any]) -> tuple[str, str]:
    a = str(
        fixture.get("participant1Name")
        or fixture.get("team_a")
        or (
            f"participant:{fixture['participant1Id']}"
            if fixture.get("participant1Id") is not None
            else ""
        )
    )
    b = str(
        fixture.get("participant2Name")
        or fixture.get("team_b")
        or (
            f"participant:{fixture['participant2Id']}"
            if fixture.get("participant2Id") is not None
            else ""
        )
    )
    return a, b


def _extract_pinnacle_prices(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect Pinnacle market prices when the provider returns them.

    Stores bookmaker prices as structured market evidence. Does **not** infer
    headshot props or Maps 1–2 player lines from unverified synthetic shapes.
    """
    prices: list[dict[str, Any]] = []
    bookmaker_odds = fixture.get("bookmakerOdds") or {}
    if not isinstance(bookmaker_odds, dict):
        return prices
    pinnacle = bookmaker_odds.get("pinnacle")
    if not isinstance(pinnacle, dict):
        return prices
    markets = pinnacle.get("markets") or {}
    if not isinstance(markets, dict):
        return prices
    for market_id, market in markets.items():
        if not isinstance(market, dict):
            continue
        outcomes = market.get("outcomes") or {}
        if not isinstance(outcomes, dict):
            continue
        for outcome_id, outcome in outcomes.items():
            if not isinstance(outcome, dict):
                continue
            players = outcome.get("players") or {"0": outcome}
            if not isinstance(players, dict):
                continue
            for player_key, row in players.items():
                if not isinstance(row, dict):
                    continue
                if "price" not in row:
                    continue
                prices.append(
                    {
                        "bookmaker": "pinnacle",
                        "market_id": str(market_id),
                        "outcome_id": str(outcome_id),
                        "player_key": str(player_key),
                        "player_name": row.get("playerName"),
                        "price": row.get("price"),
                        "price_american": row.get("priceAmerican"),
                        "bookmaker_outcome_id": row.get("bookmakerOutcomeId"),
                        "active": row.get("active"),
                        "main_line": row.get("mainLine"),
                        "limit": row.get("limit"),
                    }
                )
    return prices


def unavailable_envelope(
    reason: str,
    *,
    captured_at: str | None = None,
    attempts: list[SourceAttempt] | None = None,
    raw_ref: str | None = None,
    source: str = SOURCE_ODDSPAPI,
) -> EvidenceEnvelope:
    """Canonical envelope when OddsPapi v4 cannot supply usable JSON."""
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
    sport_id: int | None = None,
) -> EvidenceEnvelope:
    """Normalize an OddsPapi **v4** bundle (live provider or synthetic test shape).

    Expected keys (any may be missing → explicit PASS reasons via attempts):
      sports, tournaments, odds_by_tournaments,
      http_meta (list of {endpoint, status, content_type, unavailable_reason})

    Optional ``target_player_id`` + ``line`` may attach a Mason-supplied market
    line for downstream gates; this does **not** assert that OddsPapi returned
    headshot props.
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

    fixtures = [
        row
        for row in _as_list(clean.get("odds_by_tournaments"))
        if isinstance(row, dict) and row.get("fixtureId")
    ]
    if not fixtures:
        reason = "OddsPapi unavailable: no fixture objects in odds_by_tournaments"
        if any(a.outcome == "unavailable" for a in attempts):
            reason = next(a.detail for a in attempts if a.outcome == "unavailable")
        return unavailable_envelope(
            reason,
            captured_at=captured,
            attempts=attempts,
            raw_ref=raw_ref,
            source=source,
        )

    fixture = fixtures[0]
    attempts.append(
        SourceAttempt(
            source=source,
            outcome="accepted",
            detail="selected fixture from odds_by_tournaments",
        )
    )

    team_a, team_b = _team_labels(fixture)
    event_id = str(fixture.get("fixtureId") or "unknown")
    start = _start_time_iso(fixture.get("startTime") or fixture.get("start_time"), captured)
    resolved_sport = int(sport_id or fixture.get("sportId") or clean.get("sport_id") or SPORT_ID_CS2)
    pinnacle_prices = _extract_pinnacle_prices(fixture)

    market_lines: list[MarketLine] = []
    # Mason may attach an explicit line for gate testing; not a claim that OddsPapi
    # returned headshot props.
    if target_player_id is not None and line is not None:
        market_lines.append(
            MarketLine(
                player_id=str(target_player_id),
                stat="headshots",
                line=float(line),
                market_scope=MarketScope.MAPS_1_2,
            )
        )

    players: list[PlayerIdentity] = []
    if target_player_id is not None:
        players.append(
            PlayerIdentity(player_id=str(target_player_id), name=str(target_player_id), team=team_a)
        )

    map_context: dict[str, Any] = {
        "provider": source,
        "api_version": "v4",
        "sport_id": resolved_sport,
        "sport_label": SPORT_LABELS.get(resolved_sport, f"sport:{resolved_sport}"),
        "tournament_id": fixture.get("tournamentId"),
        "status_id": fixture.get("statusId"),
        "has_odds": fixture.get("hasOdds"),
        "pinnacle_prices": pinnacle_prices,
        "verified_esports_sport_ids": sorted(VERIFIED_ESPORTS_SPORT_IDS),
        "not_for_projection": bool(not_for_projection),
        "match_logs_source": "absent_from_oddspapi",
        "player_prop_claim": "none_verified_from_v4_payload",
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
        ProvenanceItem(name="sport_id", source=source, value=resolved_sport),
        ProvenanceItem(name="api_version", source=source, value="v4"),
        ProvenanceItem(
            name="pinnacle_price_count",
            source=source,
            value=len(pinnacle_prices),
        ),
    ]

    attempts.append(
        SourceAttempt(source=source, outcome="normalized", detail=f"event_id={event_id}")
    )

    status = EvidenceStatus.INCOMPLETE if synthetic or not_for_projection else EvidenceStatus.VERIFIED
    if not team_a or not team_b:
        status = EvidenceStatus.INCOMPLETE
    if not pinnacle_prices and not market_lines:
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
        evidence_completeness={
            "match_logs": False,
            "market_board": bool(pinnacle_prices) or bool(market_lines),
        },
        source_attempts=attempts,
        raw_ref=raw_ref,
        target_player_id=str(target_player_id) if target_player_id else None,
    )
