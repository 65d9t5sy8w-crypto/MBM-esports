"""BallDontLie NBA endpoint catalog derived from vendor/balldontlie/nba.yml.

Tier matrix sourced from https://nba.balldontlie.io/ account tiers documentation
and verified by live probe on 2026-11-17 against the workspace API key:

  FREE verified 200: /nba/v1/teams, /nba/v1/players, /nba/v1/games (+ by-id)
  ALL-STAR / GOAT returned HTTP 401 → remain DISABLED until access is re-verified.

Do not invent endpoints. Paths below are exactly those listed in the OpenAPI.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class AccessTier(str, Enum):
    FREE = "free"
    ALL_STAR = "all_star"
    GOAT = "goat"


@dataclass(frozen=True)
class EndpointSpec:
    path: str
    summary: str
    tier: AccessTier
    """Minimum documented tier required (from nba.balldontlie.io + OpenAPI notes)."""
    enabled: bool
    """False until live access for this key/account is verified."""
    openapi_requires_note: str | None = None


# Verified FREE on 2026-11-17 (HTTP 200 with current key).
_FREE_VERIFIED = True

# ALL-STAR / GOAT probed 2026-11-17 → HTTP 401 Unauthorized. Keep disabled.
_PAID_VERIFIED = False

ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec("/nba/v1/teams", "Get NBA teams", AccessTier.FREE, _FREE_VERIFIED),
    EndpointSpec("/nba/v1/teams/{id}", "Get specific NBA team", AccessTier.FREE, _FREE_VERIFIED),
    EndpointSpec("/nba/v1/players", "Get NBA players", AccessTier.FREE, _FREE_VERIFIED),
    EndpointSpec("/nba/v1/players/{id}", "Get specific NBA player", AccessTier.FREE, _FREE_VERIFIED),
    EndpointSpec("/nba/v1/games", "Get NBA games", AccessTier.FREE, _FREE_VERIFIED),
    EndpointSpec("/nba/v1/games/{id}", "Get specific NBA game", AccessTier.FREE, _FREE_VERIFIED),
    # ALL-STAR (docs) — probed 401
    EndpointSpec("/nba/v1/stats", "Get NBA stats", AccessTier.ALL_STAR, _PAID_VERIFIED),
    EndpointSpec(
        "/nba/v1/players/active", "Get active NBA players", AccessTier.ALL_STAR, _PAID_VERIFIED
    ),
    EndpointSpec(
        "/nba/v1/player_injuries",
        "Get NBA player injuries",
        AccessTier.ALL_STAR,
        _PAID_VERIFIED,
    ),
    # GOAT (docs / OpenAPI notes) — probed 401
    EndpointSpec(
        "/nba/v1/season_averages", "Get NBA season averages", AccessTier.GOAT, _PAID_VERIFIED
    ),
    EndpointSpec(
        "/nba/v1/season_averages/{type}",
        "Get NBA season averages by type",
        AccessTier.GOAT,
        _PAID_VERIFIED,
    ),
    EndpointSpec(
        "/nba/v1/team_season_averages/{category}",
        "Get NBA team season averages by category",
        AccessTier.GOAT,
        _PAID_VERIFIED,
    ),
    EndpointSpec("/nba/v1/standings", "Get NBA team standings", AccessTier.GOAT, _PAID_VERIFIED),
    EndpointSpec(
        "/nba/v1/box_scores/live", "Get live NBA box scores", AccessTier.GOAT, _PAID_VERIFIED
    ),
    EndpointSpec(
        "/nba/v1/box_scores", "Get NBA box scores for a specific date", AccessTier.GOAT, _PAID_VERIFIED
    ),
    EndpointSpec(
        "/nba/v1/projected_lineups",
        "Get NBA projected lineups",
        AccessTier.GOAT,
        _PAID_VERIFIED,
        openapi_requires_note="Requires the GOAT tier",
    ),
    EndpointSpec("/nba/v1/lineups", "Get NBA game lineups", AccessTier.GOAT, _PAID_VERIFIED),
    EndpointSpec("/nba/v1/leaders", "Get NBA stat leaders", AccessTier.GOAT, _PAID_VERIFIED),
    EndpointSpec("/nba/v2/odds", "Get NBA betting odds", AccessTier.GOAT, _PAID_VERIFIED),
    EndpointSpec(
        "/nba/v2/odds/opening",
        "Get NBA opening betting odds",
        AccessTier.GOAT,
        _PAID_VERIFIED,
        openapi_requires_note="Requires GOAT tier",
    ),
    EndpointSpec(
        "/nba/v2/odds/player_props",
        "Get NBA player prop betting odds",
        AccessTier.GOAT,
        _PAID_VERIFIED,
    ),
    EndpointSpec(
        "/nba/v2/odds/player_props/opening",
        "Get NBA opening player prop odds",
        AccessTier.GOAT,
        _PAID_VERIFIED,
        openapi_requires_note="Requires GOAT tier",
    ),
    EndpointSpec(
        "/nba/v2/stats/advanced",
        "Get NBA advanced stats (V2)",
        AccessTier.GOAT,
        _PAID_VERIFIED,
    ),
    EndpointSpec(
        "/nba/v1/contracts/teams",
        "Get NBA player contracts by team",
        AccessTier.GOAT,
        _PAID_VERIFIED,
    ),
    EndpointSpec(
        "/nba/v1/contracts/players", "Get NBA player contracts", AccessTier.GOAT, _PAID_VERIFIED
    ),
    EndpointSpec(
        "/nba/v1/contracts/players/aggregate",
        "Get aggregated NBA player contract data",
        AccessTier.GOAT,
        _PAID_VERIFIED,
    ),
    EndpointSpec(
        "/nba/v1/dfs/slates",
        "Get NBA DFS slates",
        AccessTier.GOAT,
        _PAID_VERIFIED,
        openapi_requires_note="Requires GOAT tier",
    ),
    EndpointSpec(
        "/nba/v1/dfs/slates/{id}",
        "Get a NBA DFS slate",
        AccessTier.GOAT,
        _PAID_VERIFIED,
        openapi_requires_note="Requires GOAT tier",
    ),
    EndpointSpec(
        "/nba/v1/dfs/draftables",
        "Get NBA DFS draftables",
        AccessTier.GOAT,
        _PAID_VERIFIED,
        openapi_requires_note="Requires GOAT tier",
    ),
    EndpointSpec("/nba/v1/plays", "Get NBA play-by-play data", AccessTier.GOAT, _PAID_VERIFIED),
    EndpointSpec(
        "/nba/v1/shot_charts",
        "Get NBA shot charts",
        AccessTier.GOAT,
        _PAID_VERIFIED,
        openapi_requires_note="Requires NBA GOAT or ALL-ACCESS",
    ),
    EndpointSpec(
        "/nba/v1/stats/tracking",
        "Get NBA game tracking stats",
        AccessTier.GOAT,
        _PAID_VERIFIED,
        openapi_requires_note="Requires GOAT or ALL-ACCESS",
    ),
    EndpointSpec(
        "/nba/v1/stats/defense",
        "Get NBA game shot defense",
        AccessTier.GOAT,
        _PAID_VERIFIED,
        openapi_requires_note="Requires GOAT or ALL-ACCESS",
    ),
    EndpointSpec(
        "/nba/v1/stats/shooting",
        "Get NBA game shooting splits",
        AccessTier.GOAT,
        _PAID_VERIFIED,
        openapi_requires_note="Requires GOAT or ALL-ACCESS",
    ),
    EndpointSpec(
        "/nba/v1/lineup_stats",
        "Get NBA lineup stats",
        AccessTier.GOAT,
        _PAID_VERIFIED,
        openapi_requires_note="Requires GOAT or ALL-ACCESS",
    ),
    EndpointSpec(
        "/nba/v1/matchups",
        "Get NBA matchups",
        AccessTier.GOAT,
        _PAID_VERIFIED,
        openapi_requires_note="Requires GOAT or ALL-ACCESS",
    ),
    EndpointSpec(
        "/nba/v1/win_probabilities",
        "Get NBA win probabilities",
        AccessTier.GOAT,
        _PAID_VERIFIED,
        openapi_requires_note="Requires GOAT or ALL-ACCESS",
    ),
)

_BY_PATH: Mapping[str, EndpointSpec] = {e.path: e for e in ENDPOINTS}

ENABLED_PATHS: frozenset[str] = frozenset(e.path for e in ENDPOINTS if e.enabled)
DISABLED_PATHS: frozenset[str] = frozenset(e.path for e in ENDPOINTS if not e.enabled)

# Template paths used for authorization (strip concrete ids).
_TEMPLATE_PREFIXES = (
    "/nba/v1/teams/",
    "/nba/v1/players/",
    "/nba/v1/games/",
    "/nba/v1/season_averages/",
    "/nba/v1/team_season_averages/",
    "/nba/v1/dfs/slates/",
)


def _path_only(path: str) -> str:
    """Strip query/fragment before catalog matching."""
    # Avoid importing urllib here for a tiny split; keep local.
    bare = path.split("?", 1)[0].split("#", 1)[0]
    return bare or path


def _numeric_id(segment: str) -> bool:
    return segment.isdigit()


def canonicalize_path(path: str) -> str:
    """Map a concrete request path to its OpenAPI template form when applicable."""
    path = _path_only(path)
    if path in _BY_PATH:
        return path
    if path.startswith("/nba/v1/teams/") and path.count("/") == 4:
        seg = path.rsplit("/", 1)[-1]
        if _numeric_id(seg):
            return "/nba/v1/teams/{id}"
        return path
    if path.startswith("/nba/v1/players/") and path.count("/") == 4:
        seg = path.rsplit("/", 1)[-1]
        # Distinct catalog path — never treat "active" as a player id.
        if seg == "active":
            return "/nba/v1/players/active"
        if _numeric_id(seg):
            return "/nba/v1/players/{id}"
        return path
    if path.startswith("/nba/v1/games/") and path.count("/") == 4:
        seg = path.rsplit("/", 1)[-1]
        if _numeric_id(seg):
            return "/nba/v1/games/{id}"
        return path
    if path.startswith("/nba/v1/season_averages/") and path.count("/") == 4:
        return "/nba/v1/season_averages/{type}"
    if path.startswith("/nba/v1/team_season_averages/") and path.count("/") == 4:
        return "/nba/v1/team_season_averages/{category}"
    if path.startswith("/nba/v1/dfs/slates/") and path.count("/") == 4:
        seg = path.rsplit("/", 1)[-1]
        if _numeric_id(seg):
            return "/nba/v1/dfs/slates/{id}"
        return path
    return path


def get_endpoint(path: str) -> EndpointSpec | None:
    return _BY_PATH.get(canonicalize_path(path))


def is_enabled(path: str) -> bool:
    spec = get_endpoint(path)
    return bool(spec and spec.enabled)


def disabled_reason(path: str) -> str:
    spec = get_endpoint(path)
    if spec is None:
        return (
            f"BallDontLie path {path!r} is not in the OpenAPI NBA catalog "
            "(refusing invented endpoint)"
        )
    if spec.enabled:
        return ""
    note = f" ({spec.openapi_requires_note})" if spec.openapi_requires_note else ""
    return (
        f"BallDontLie endpoint {spec.path} disabled: requires {spec.tier.value} "
        f"access; not verified for this account{note}"
    )
