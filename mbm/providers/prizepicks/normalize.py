"""Normalize PrizePicks projections JSON into board records (no scoring)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

SOURCE_BROWSER_BRIDGE = "prizepicks_browser_bridge"
SOURCE_PROVIDER = "prizepicks_provider"
SOURCE_LAST_KNOWN_GOOD = "prizepicks_last_known_good"
SOURCE_NONE = "none"

# League name fragments -> sport tags used for scoped capture filtering.
SPORT_ALIASES: dict[str, tuple[str, ...]] = {
    "cs2": ("cs2", "cs:go", "counter-strike", "counter strike"),
    "valorant": ("valorant",),
    "cod": ("cod", "call of duty", "warzone"),
    "lol": ("lol", "league of legends"),
    "dota": ("dota", "dota 2", "dota2"),
    "mlb": ("mlb", "baseball"),
    "nfl": ("nfl", "football"),
}


@dataclass(frozen=True)
class NormalizedProp:
    """One PrizePicks projection as a normalized live-board record."""

    prop_id: str
    player_id: str
    player_name: str
    team: str
    league: str
    sport: str
    stat: str
    line: float | None
    start_time: str | None
    identity_status: str  # always unresolved from name alone
    status: str  # ACTIVE | REMOVED
    source: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _index_included(included: list[Any]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in included:
        if not isinstance(row, dict):
            continue
        rtype = str(row.get("type", ""))
        rid = str(row.get("id", ""))
        if rtype and rid:
            out[(rtype, rid)] = row
    return out


def _rel_id(item: dict[str, Any], rel_name: str) -> str | None:
    rel = (item.get("relationships") or {}).get(rel_name) or {}
    data = rel.get("data")
    if isinstance(data, dict) and data.get("id") is not None:
        return str(data["id"])
    return None


def _sport_tag(league_name: str) -> str:
    low = league_name.lower()
    for tag, aliases in SPORT_ALIASES.items():
        if any(a in low for a in aliases):
            return tag
    return "unknown"


def normalize_projections_payload(
    payload: dict[str, Any],
    *,
    source: str = SOURCE_BROWSER_BRIDGE,
    sports_filter: list[str] | None = None,
) -> list[NormalizedProp]:
    """Map PrizePicks `data`/`included` into normalized props.

    Player identity stays unresolved — never merge by display name alone.
    """
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("PrizePicks payload requires a data array")

    included = payload.get("included") or []
    if not isinstance(included, list):
        included = []
    by_id = _index_included(included)

    allowed = {s.lower() for s in sports_filter} if sports_filter else None
    records: list[NormalizedProp] = []

    for item in data:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")).lower() not in {"projection", "projections"}:
            # Still accept generic projection-like rows with attributes.line_score.
            attrs = item.get("attributes") or {}
            if "line_score" not in attrs and "stat_type" not in attrs:
                continue

        prop_id = str(item.get("id", "")).strip()
        if not prop_id:
            continue
        attrs = item.get("attributes") or {}
        player_key = _rel_id(item, "new_player") or _rel_id(item, "player")
        league_key = _rel_id(item, "league")

        player_row = by_id.get(("new_player", player_key or ""), {}) or by_id.get(
            ("player", player_key or ""), {}
        )
        league_row = by_id.get(("league", league_key or ""), {})
        player_attrs = (player_row or {}).get("attributes") or {}
        league_attrs = (league_row or {}).get("attributes") or {}

        league_name = str(
            league_attrs.get("name")
            or attrs.get("league")
            or attrs.get("league_name")
            or ""
        )
        sport = _sport_tag(league_name)
        # Filter after capture / during normalize — scoped boards keep other sports
        # untouched in active state (service never REMOVEs outside scope).
        if allowed is not None and sport not in allowed:
            continue

        line_raw = attrs.get("line_score", attrs.get("line"))
        try:
            line = float(line_raw) if line_raw is not None else None
        except (TypeError, ValueError):
            line = None

        player_id = str(player_key or "")
        records.append(
            NormalizedProp(
                prop_id=prop_id,
                player_id=player_id,
                player_name=str(player_attrs.get("name") or attrs.get("name") or ""),
                team=str(player_attrs.get("team_name") or player_attrs.get("team") or ""),
                league=league_name,
                sport=sport,
                stat=str(attrs.get("stat_type") or attrs.get("stat") or ""),
                line=line,
                start_time=(
                    str(attrs["start_time"]) if attrs.get("start_time") is not None else None
                ),
                identity_status="unresolved",
                status="ACTIVE",
                source=source,
            )
        )
    return records
