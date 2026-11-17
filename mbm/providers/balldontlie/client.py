"""BallDontLie NBA HTTP adapter — OpenAPI-documented operations only.

Auth: ``Authorization`` header from ``BALLDONTLIE_API_KEY`` (OpenAPI ApiKeyAuth).
Never places credentials in query strings, logs, or persisted URL metadata.
"""

from __future__ import annotations

import http.client
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

from mbm import __version__
from mbm.providers.balldontlie.endpoints import (
    DISABLED_PATHS,
    ENABLED_PATHS,
    canonicalize_path,
    disabled_reason,
    get_endpoint,
    is_enabled,
)

BASE_URL = "https://api.balldontlie.io"
USER_AGENT = f"MBM-esports/{__version__} (+https://github.com/65d9t5sy8w-crypto/MBM-esports)"
API_KEY_ENV = "BALLDONTLIE_API_KEY"

# Redact full Authorization values (optional quotes + optional Bearer prefix).
_AUTH_HEADER_RE = re.compile(
    r"(?i)([\"']?authorization[\"']?\s*[:=]\s*)([\"']?)(?:bearer\s+)?([^\"'\s,}]+)([\"']?)"
)
_BEARER_RE = re.compile(r"(?i)(bearer\s+)(\S+)")


def redact_secrets(text: str) -> str:
    """Redact Authorization/Bearer material from any string before logging."""
    out = _AUTH_HEADER_RE.sub(r"\1\2REDACTED\4", text)
    out = _BEARER_RE.sub(r"\1REDACTED", out)
    return out


def redact_url(url: str) -> str:
    """URLs must never carry the API key; still scrub query leftovers defensively."""
    parsed = urllib.parse.urlsplit(url)
    if not parsed.query:
        return url
    pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    scrubbed = []
    for k, v in pairs:
        if k.lower() in {"apikey", "api_key", "authorization", "token"}:
            scrubbed.append((k, "REDACTED"))
        else:
            scrubbed.append((k, v))
    return urllib.parse.urlunsplit(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(scrubbed, doseq=True),
            parsed.fragment,
        )
    )


@dataclass(frozen=True)
class BallDontLieHttpResult:
    ok: bool
    status: int
    content_type: str
    body: bytes
    url: str
    path: str
    json_body: Any | None
    unavailable_reason: str | None
    enabled: bool

    @property
    def available(self) -> bool:
        return (
            self.enabled
            and self.ok
            and self.json_body is not None
            and self.unavailable_reason is None
        )


def _is_json_content_type(content_type: str) -> bool:
    ct = (content_type or "").split(";")[0].strip().lower()
    return ct in {"application/json", "application/vnd.api+json", "text/json"}


class BallDontLieNbaAdapter:
    """Synchronous BallDontLie NBA client (stdlib urllib).

    Production calls are limited to endpoints marked ``enabled`` in
    :mod:`mbm.providers.balldontlie.endpoints`. Paid / unverified paths return
    an unavailable result without contacting the network.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        timeout_s: float = 20.0,
        allow_disabled_probe: bool = False,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get(API_KEY_ENV, "")
        self.api_key = str(key or "").strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        # When True, disabled endpoints may be probed once for access verification.
        # Default False — paid endpoints stay off until explicitly re-enabled in catalog.
        self.allow_disabled_probe = allow_disabled_probe

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }

    def _transport_unavailable(
        self,
        *,
        path: str,
        safe_url: str,
        enabled: bool,
        detail: str,
    ) -> BallDontLieHttpResult:
        return BallDontLieHttpResult(
            ok=False,
            status=0,
            content_type="",
            body=b"",
            url=safe_url,
            path=path,
            json_body=None,
            unavailable_reason=f"BallDontLie unavailable: transport error ({detail})",
            enabled=enabled,
        )

    def request(
        self,
        path: str,
        params: Mapping[str, Any] | None = None,
        *,
        force_probe: bool = False,
    ) -> BallDontLieHttpResult:
        # Strip query from path before catalog matching (callers may pass ?...).
        path_only = urllib.parse.urlsplit(path).path or path
        canon = canonicalize_path(path_only)
        spec = get_endpoint(path_only)
        if spec is None:
            raise ValueError(
                f"BallDontLieNbaAdapter refuses unknown path {path!r}; "
                "only OpenAPI /nba/* operations are allowed"
            )

        enabled = is_enabled(path_only)
        if not enabled and not (force_probe and self.allow_disabled_probe):
            reason = disabled_reason(path_only)
            return BallDontLieHttpResult(
                ok=False,
                status=0,
                content_type="",
                body=b"",
                url=redact_url(f"{self.base_url}{path_only}"),
                path=canon,
                json_body=None,
                unavailable_reason=reason,
                enabled=False,
            )

        if not self.api_key:
            return BallDontLieHttpResult(
                ok=False,
                status=0,
                content_type="",
                body=b"",
                url=redact_url(f"{self.base_url}{path_only}"),
                path=canon,
                json_body=None,
                unavailable_reason=(
                    f"BallDontLie unavailable: missing API key "
                    f"(set {API_KEY_ENV} or pass api_key=)"
                ),
                enabled=enabled,
            )

        query_items: list[tuple[str, str]] = []
        for k, v in (params or {}).items():
            if isinstance(v, (list, tuple)):
                for item in v:
                    query_items.append((k, str(item)))
            elif v is None:
                continue
            else:
                query_items.append((k, str(v)))
        query = urllib.parse.urlencode(query_items, doseq=True)
        url = f"{self.base_url}{path_only}"
        if query:
            url = f"{url}?{query}"
        safe_url = redact_url(url)
        headers = self._headers()
        req = urllib.request.Request(url, headers=headers, method="GET")
        # Keep Authorization off redirected requests (origin/scheme change risk).
        req.add_unredirected_header("Authorization", self.api_key)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                status = int(getattr(resp, "status", 200))
                content_type = resp.headers.get("Content-Type", "")
                try:
                    body = resp.read()
                except (http.client.IncompleteRead, OSError, ValueError) as exc:
                    return self._transport_unavailable(
                        path=canon,
                        safe_url=safe_url,
                        enabled=enabled,
                        detail=f"body read failed: {exc}",
                    )
        except urllib.error.HTTPError as exc:
            try:
                body = exc.read() if exc.fp is not None else b""
            except (http.client.IncompleteRead, OSError, ValueError) as read_exc:
                return self._transport_unavailable(
                    path=canon,
                    safe_url=safe_url,
                    enabled=enabled,
                    detail=f"HTTP {exc.code} body read failed: {read_exc}",
                )
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            detail = body.decode("utf-8", errors="replace")[:200]
            detail = redact_secrets(detail)
            # Also scrub raw api key if it somehow appears bare.
            if self.api_key and self.api_key in detail:
                detail = detail.replace(self.api_key, "REDACTED")
            return BallDontLieHttpResult(
                ok=False,
                status=int(exc.code),
                content_type=content_type,
                body=body,
                url=safe_url,
                path=canon,
                json_body=None,
                unavailable_reason=(
                    f"BallDontLie unavailable: HTTP {exc.code} "
                    f"content_type={content_type or 'missing'} detail={detail!r}"
                ),
                enabled=enabled,
            )
        except TimeoutError as exc:
            return self._transport_unavailable(
                path=canon, safe_url=safe_url, enabled=enabled, detail=str(exc)
            )
        except urllib.error.URLError as exc:
            return self._transport_unavailable(
                path=canon, safe_url=safe_url, enabled=enabled, detail=str(exc.reason)
            )
        except http.client.IncompleteRead as exc:
            return self._transport_unavailable(
                path=canon, safe_url=safe_url, enabled=enabled, detail=str(exc)
            )

        if status != 200:
            return BallDontLieHttpResult(
                ok=False,
                status=status,
                content_type=content_type,
                body=body,
                url=safe_url,
                path=canon,
                json_body=None,
                unavailable_reason=(
                    f"BallDontLie unavailable: HTTP {status} "
                    f"content_type={content_type or 'missing'}"
                ),
                enabled=enabled,
            )
        if not _is_json_content_type(content_type):
            return BallDontLieHttpResult(
                ok=False,
                status=status,
                content_type=content_type,
                body=body,
                url=safe_url,
                path=canon,
                json_body=None,
                unavailable_reason=(
                    f"BallDontLie unavailable: HTTP {status} "
                    f"non-JSON content_type={content_type or 'missing'}"
                ),
                enabled=enabled,
            )
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return BallDontLieHttpResult(
                ok=False,
                status=status,
                content_type=content_type,
                body=body,
                url=safe_url,
                path=canon,
                json_body=None,
                unavailable_reason=f"BallDontLie unavailable: JSON parse failed ({exc})",
                enabled=enabled,
            )
        return BallDontLieHttpResult(
            ok=True,
            status=status,
            content_type=content_type,
            body=body,
            url=safe_url,
            path=canon,
            json_body=parsed,
            unavailable_reason=None,
            enabled=enabled,
        )

    # --- Free (enabled) helpers -------------------------------------------------
    def teams(self, **params: Any) -> BallDontLieHttpResult:
        return self.request("/nba/v1/teams", params)

    def team(self, team_id: int) -> BallDontLieHttpResult:
        return self.request(f"/nba/v1/teams/{int(team_id)}")

    def players(self, **params: Any) -> BallDontLieHttpResult:
        return self.request("/nba/v1/players", params)

    def player(self, player_id: int) -> BallDontLieHttpResult:
        return self.request(f"/nba/v1/players/{int(player_id)}")

    def games(self, **params: Any) -> BallDontLieHttpResult:
        return self.request("/nba/v1/games", params)

    def game(self, game_id: int) -> BallDontLieHttpResult:
        return self.request(f"/nba/v1/games/{int(game_id)}")

    # --- Paid (disabled until verified) helpers ---------------------------------
    def stats(self, **params: Any) -> BallDontLieHttpResult:
        return self.request("/nba/v1/stats", params)

    def player_injuries(self, **params: Any) -> BallDontLieHttpResult:
        return self.request("/nba/v1/player_injuries", params)

    def advanced_stats(self, **params: Any) -> BallDontLieHttpResult:
        return self.request("/nba/v2/stats/advanced", params)

    def odds(self, **params: Any) -> BallDontLieHttpResult:
        return self.request("/nba/v2/odds", params)

    def player_props(self, **params: Any) -> BallDontLieHttpResult:
        return self.request("/nba/v2/odds/player_props", params)

    def lineups(self, **params: Any) -> BallDontLieHttpResult:
        return self.request("/nba/v1/lineups", params)

    def projected_lineups(self, **params: Any) -> BallDontLieHttpResult:
        return self.request("/nba/v1/projected_lineups", params)


__all__ = [
    "API_KEY_ENV",
    "BASE_URL",
    "BallDontLieHttpResult",
    "BallDontLieNbaAdapter",
    "DISABLED_PATHS",
    "ENABLED_PATHS",
    "USER_AGENT",
    "redact_secrets",
    "redact_url",
]
