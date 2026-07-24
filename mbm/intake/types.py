"""Canonical intake types consumed by universal MBM modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class MarketScope(str, Enum):
    MAP_1 = "map_1"
    MAPS_1_2 = "maps_1_2"
    FULL_SERIES = "full_series"


class IdentityStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class EvidenceStatus(str, Enum):
    VERIFIED = "verified"
    STALE = "stale"
    INCOMPLETE = "incomplete"
    UNRESOLVED = "unresolved"


class EconomyContext(str, Enum):
    PISTOL = "pistol"
    ECO = "eco"
    ANTI_ECO = "anti_eco"
    FORCE_BUY = "force_buy"
    FULL_BUY = "full_buy"


class Recommendation(str, Enum):
    OVER = "OVER"
    UNDER = "UNDER"
    PASS = "PASS"


ALLOWED_ACTIONS = frozenset({r.value for r in Recommendation})
DEFAULT_MARKET_SCOPE = MarketScope.MAPS_1_2
SECRET_KEY_FRAGMENTS = (
    "authorization",
    "cookie",
    "set-cookie",
    "token",
    "api_key",
    "apikey",
    "rgapi",
    "x-riot-token",
    "session",
    "password",
    "secret",
)


@dataclass(frozen=True)
class FixtureIdentity:
    event_id: str
    team_a: str
    team_b: str
    start_time: str
    format: str
    market_scope: MarketScope = DEFAULT_MARKET_SCOPE


@dataclass(frozen=True)
class PlayerIdentity:
    player_id: str
    name: str
    team: str


@dataclass(frozen=True)
class MatchLogSample:
    match_id: str
    market_scope: MarketScope
    kills: float
    deaths: float
    assists: float
    headshots: float
    opening_kills: float
    opening_deaths: float
    rounds_played: float
    ct_rounds: float
    t_rounds: float
    economy: tuple[EconomyContext, ...] = ()


@dataclass(frozen=True)
class MarketLine:
    player_id: str
    stat: str
    line: float
    market_scope: MarketScope


@dataclass(frozen=True)
class ProvenanceItem:
    name: str
    source: str
    value: Any
    transform: str | None = None


@dataclass(frozen=True)
class SourceAttempt:
    source: str
    outcome: str
    detail: str


@dataclass
class EvidenceEnvelope:
    source: str
    captured_at: str
    fixture: FixtureIdentity
    players: list[PlayerIdentity]
    match_logs: list[MatchLogSample]
    map_context: dict[str, Any]
    market_lines: list[MarketLine]
    evidence_status: EvidenceStatus
    identity_status: IdentityStatus = IdentityStatus.UNRESOLVED
    provenance: list[ProvenanceItem] = field(default_factory=list)
    evidence_completeness: dict[str, bool] = field(default_factory=dict)
    source_attempts: list[SourceAttempt] = field(default_factory=list)
    raw_ref: str | None = None
    target_player_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> EvidenceEnvelope:
        fixture_raw = payload["fixture"]
        scope = MarketScope(fixture_raw.get("market_scope", DEFAULT_MARKET_SCOPE.value))
        fixture = FixtureIdentity(
            event_id=str(fixture_raw["event_id"]),
            team_a=str(fixture_raw["team_a"]),
            team_b=str(fixture_raw["team_b"]),
            start_time=str(fixture_raw["start_time"]),
            format=str(fixture_raw["format"]),
            market_scope=scope,
        )
        players = [
            PlayerIdentity(
                player_id=str(p["player_id"]),
                name=str(p["name"]),
                team=str(p["team"]),
            )
            for p in payload.get("players", [])
        ]
        logs: list[MatchLogSample] = []
        for row in payload.get("match_logs", []):
            econ = tuple(EconomyContext(e) for e in row.get("economy", []))
            logs.append(
                MatchLogSample(
                    match_id=str(row["match_id"]),
                    market_scope=MarketScope(row["market_scope"]),
                    kills=float(row["kills"]),
                    deaths=float(row["deaths"]),
                    assists=float(row["assists"]),
                    headshots=float(row["headshots"]),
                    opening_kills=float(row.get("opening_kills", 0)),
                    opening_deaths=float(row.get("opening_deaths", 0)),
                    rounds_played=float(row.get("rounds_played", 0)),
                    ct_rounds=float(row.get("ct_rounds", 0)),
                    t_rounds=float(row.get("t_rounds", 0)),
                    economy=econ,
                )
            )
        lines = [
            MarketLine(
                player_id=str(m["player_id"]),
                stat=str(m["stat"]),
                line=float(m["line"]),
                market_scope=MarketScope(m["market_scope"]),
            )
            for m in payload.get("market_lines", [])
        ]
        provenance = [
            ProvenanceItem(
                name=str(p["name"]),
                source=str(p["source"]),
                value=p.get("value"),
                transform=p.get("transform"),
            )
            for p in payload.get("provenance", [])
        ]
        attempts = [
            SourceAttempt(
                source=str(a["source"]),
                outcome=str(a["outcome"]),
                detail=str(a["detail"]),
            )
            for a in payload.get("source_attempts", [])
        ]
        identity = IdentityStatus(payload.get("identity_status", IdentityStatus.UNRESOLVED.value))
        status = EvidenceStatus(payload.get("evidence_status", EvidenceStatus.INCOMPLETE.value))
        return cls(
            source=str(payload["source"]),
            captured_at=str(payload["captured_at"]),
            fixture=fixture,
            players=players,
            match_logs=logs,
            map_context=dict(payload.get("map_context", {})),
            market_lines=lines,
            evidence_status=status,
            identity_status=identity,
            provenance=provenance,
            evidence_completeness=dict(payload.get("evidence_completeness", {})),
            source_attempts=attempts,
            raw_ref=payload.get("raw_ref"),
            target_player_id=payload.get("target_player_id"),
        )
