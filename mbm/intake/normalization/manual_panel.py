"""Translate Mason/manual drops into canonical EvidenceEnvelope."""

from __future__ import annotations

from typing import Any

from mbm.intake.types import (
    DEFAULT_MARKET_SCOPE,
    SECRET_KEY_FRAGMENTS,
    EconomyContext,
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


def strip_secrets(payload: Any) -> Any:
    """Recursively drop secret-bearing keys. Never persist tokens/cookies."""
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            key_l = str(key).lower()
            if any(frag in key_l for frag in SECRET_KEY_FRAGMENTS):
                continue
            if isinstance(value, str) and value.upper().startswith("RGAPI-"):
                continue
            cleaned[key] = strip_secrets(value)
        return cleaned
    if isinstance(payload, list):
        return [strip_secrets(item) for item in payload]
    return payload


def normalize_manual_panel(
    payload: dict[str, Any],
    *,
    raw_ref: str | None = None,
) -> EvidenceEnvelope:
    """Normalize a manual/provider-neutral panel into EvidenceEnvelope."""
    clean = strip_secrets(payload)
    source = str(clean.get("source", "manual-drop"))
    captured_at = str(clean["captured_at"])

    if "fixture" in clean:
        fixture_raw = clean["fixture"]
    else:
        # Legacy thin panel shape from early scaffold.
        fixture_raw = {
            "event_id": clean.get("match_id") or clean.get("event_id"),
            "team_a": clean.get("team_a", ""),
            "team_b": clean.get("team_b", ""),
            "start_time": clean.get("start_time", captured_at),
            "format": clean.get("format", "bo3"),
            "market_scope": clean.get("market_scope")
            or (
                "maps_1_2"
                if clean.get("map_window", {}).get("start_map") == 1
                and clean.get("map_window", {}).get("end_map") == 2
                else DEFAULT_MARKET_SCOPE.value
            ),
        }

    scope = MarketScope(fixture_raw.get("market_scope", DEFAULT_MARKET_SCOPE.value))
    fixture = FixtureIdentity(
        event_id=str(fixture_raw["event_id"]),
        team_a=str(fixture_raw.get("team_a", "")),
        team_b=str(fixture_raw.get("team_b", "")),
        start_time=str(fixture_raw.get("start_time", captured_at)),
        format=str(fixture_raw.get("format", "bo3")),
        market_scope=scope,
    )

    players = [
        PlayerIdentity(
            player_id=str(p["player_id"]),
            name=str(p.get("name", p["player_id"])),
            team=str(p.get("team", "")),
        )
        for p in clean.get("players", [])
    ]

    logs: list[MatchLogSample] = []
    for row in clean.get("match_logs", []):
        econ = tuple(EconomyContext(e) for e in row.get("economy", []))
        logs.append(
            MatchLogSample(
                match_id=str(row["match_id"]),
                market_scope=MarketScope(row.get("market_scope", scope.value)),
                kills=float(row["kills"]),
                deaths=float(row.get("deaths", 0)),
                assists=float(row.get("assists", 0)),
                headshots=float(row["headshots"]),
                opening_kills=float(row.get("opening_kills", 0)),
                opening_deaths=float(row.get("opening_deaths", 0)),
                rounds_played=float(row.get("rounds_played", 0)),
                ct_rounds=float(row.get("ct_rounds", 0)),
                t_rounds=float(row.get("t_rounds", 0)),
                economy=econ,
            )
        )

    market_lines: list[MarketLine] = []
    for m in clean.get("market_lines", []):
        market_lines.append(
            MarketLine(
                player_id=str(m["player_id"]),
                stat=str(m["stat"]),
                line=float(m["line"]),
                market_scope=MarketScope(m.get("market_scope", scope.value)),
            )
        )
    # Legacy single-line panel
    if not market_lines and "line" in clean:
        player_id = str(clean.get("target_player_id") or clean.get("player_id") or "")
        market_lines.append(
            MarketLine(
                player_id=player_id,
                stat="headshots",
                line=float(clean["line"]),
                market_scope=scope,
            )
        )

    map_context = dict(clean.get("map_context", {}))
    if not map_context and "features" in clean:
        features = clean["features"]
        map_context = {
            "map_pool": features.get("map_pool", []),
            "sample_matches": features.get("sample_matches"),
        }

    provenance = [
        ProvenanceItem(
            name="source",
            source=source,
            value=source,
        ),
        ProvenanceItem(
            name="captured_at",
            source=source,
            value=captured_at,
        ),
        ProvenanceItem(
            name="market_scope",
            source=source,
            value=scope.value,
        ),
    ]
    for key, value in map_context.items():
        provenance.append(ProvenanceItem(name=f"map_context.{key}", source=source, value=value))

    attempts = [
        SourceAttempt(source=source, outcome="accepted", detail="manual/normalized panel"),
    ]
    for a in clean.get("source_attempts", []):
        attempts.append(
            SourceAttempt(
                source=str(a["source"]),
                outcome=str(a["outcome"]),
                detail=str(a.get("detail", "")),
            )
        )

    status = EvidenceStatus(clean.get("evidence_status", EvidenceStatus.VERIFIED.value))
    return EvidenceEnvelope(
        source=source,
        captured_at=captured_at,
        fixture=fixture,
        players=players,
        match_logs=logs,
        map_context=map_context,
        market_lines=market_lines,
        evidence_status=status,
        identity_status=IdentityStatus.UNRESOLVED,
        provenance=provenance,
        source_attempts=attempts,
        raw_ref=raw_ref,
        target_player_id=clean.get("target_player_id")
        or (market_lines[0].player_id if market_lines else None),
    )
