"""Honest BO3.gg HTTP client — no browser impersonation."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

from mbm import __version__

BASE_URL = "https://api.bo3.gg/api/v1"
USER_AGENT = f"MBM-esports/{__version__} (+https://github.com/65d9t5sy8w-crypto/MBM-esports)"

# Shared CS2 discipline + widget includes (from endpoint contract).
_CS2 = "1"
_MATCH_WITH = "teams,tournament,games,streams"


@dataclass(frozen=True)
class Bo3HttpResult:
    """Single-shot HTTP outcome. Never retries."""

    ok: bool
    status: int
    content_type: str
    body: bytes
    url: str
    json_body: Any | None
    unavailable_reason: str | None

    @property
    def available(self) -> bool:
        return self.ok and self.json_body is not None and self.unavailable_reason is None


def _is_json_content_type(content_type: str) -> bool:
    ct = (content_type or "").split(";")[0].strip().lower()
    return ct in {"application/json", "application/vnd.api+json", "text/json"}


class Bo3Client:
    """Synchronous BO3 client using stdlib urllib only."""

    def __init__(self, *, base_url: str = BASE_URL, timeout_s: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        # Honest identity only — no Origin/Referer/sec-ch-ua/Chrome spoofing.
        return {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }

    def request(self, path: str, params: Mapping[str, Any] | None = None) -> Bo3HttpResult:
        query = urllib.parse.urlencode({k: str(v) for k, v in (params or {}).items()}, doseq=True)
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                status = int(getattr(resp, "status", 200))
                content_type = resp.headers.get("Content-Type", "")
                body = resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read() if exc.fp is not None else b""
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            return Bo3HttpResult(
                ok=False,
                status=int(exc.code),
                content_type=content_type,
                body=body,
                url=url,
                json_body=None,
                unavailable_reason=(
                    f"BO3 unavailable: HTTP {exc.code} content_type={content_type or 'missing'}"
                ),
            )
        except urllib.error.URLError as exc:
            return Bo3HttpResult(
                ok=False,
                status=0,
                content_type="",
                body=b"",
                url=url,
                json_body=None,
                unavailable_reason=f"BO3 unavailable: transport error ({exc.reason})",
            )

        if status != 200:
            return Bo3HttpResult(
                ok=False,
                status=status,
                content_type=content_type,
                body=body,
                url=url,
                json_body=None,
                unavailable_reason=(
                    f"BO3 unavailable: HTTP {status} content_type={content_type or 'missing'}"
                ),
            )
        if not _is_json_content_type(content_type):
            return Bo3HttpResult(
                ok=False,
                status=status,
                content_type=content_type,
                body=body,
                url=url,
                json_body=None,
                unavailable_reason=(
                    f"BO3 unavailable: HTTP {status} non-JSON content_type={content_type or 'missing'}"
                ),
            )
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return Bo3HttpResult(
                ok=False,
                status=status,
                content_type=content_type,
                body=body,
                url=url,
                json_body=None,
                unavailable_reason=f"BO3 unavailable: JSON parse failed ({exc})",
            )
        return Bo3HttpResult(
            ok=True,
            status=status,
            content_type=content_type,
            body=body,
            url=url,
            json_body=parsed,
            unavailable_reason=None,
        )

    def upcoming_matches(self, *, limit: int = 50) -> Bo3HttpResult:
        return self.request(
            "/matches",
            {
                "scope": "widget-matches",
                "page[offset]": 0,
                "page[limit]": limit,
                "sort": "tier_rank,-start_date",
                "filter[matches.status][in]": "upcoming",
                "filter[matches.discipline_id][eq]": _CS2,
                "with": _MATCH_WITH,
            },
        )

    def live_matches(self, *, limit: int = 50) -> Bo3HttpResult:
        return self.request(
            "/matches",
            {
                "scope": "widget-matches",
                "page[offset]": 0,
                "page[limit]": limit,
                "sort": "tier_rank,-start_date",
                "filter[matches.status][in]": "current",
                "filter[matches.discipline_id][eq]": _CS2,
                "with": _MATCH_WITH,
            },
        )

    def finished_matches(self, *, limit: int = 50) -> Bo3HttpResult:
        return self.request(
            "/matches",
            {
                "scope": "widget-matches",
                "page[offset]": 0,
                "page[limit]": limit,
                "sort": "tier_rank,-start_date",
                "filter[matches.status][in]": "finished",
                "filter[matches.discipline_id][eq]": _CS2,
                "with": _MATCH_WITH,
            },
        )

    def match_detail(self, slug: str) -> Bo3HttpResult:
        return self.request(
            f"/matches/{urllib.parse.quote(slug, safe='')}",
            {
                "scope": "show-match",
                "with": "games,streams,teams,tournament_deep,stage",
            },
        )

    def player_match_history(self, player_id: int | str, *, limit: int = 50) -> Bo3HttpResult:
        return self.request(
            "/matches",
            {
                "scope": "widget-matches",
                "page[offset]": 0,
                "page[limit]": limit,
                "sort": "-start_date",
                "filter[matches.status][in]": "finished,defwin,upcoming,current",
                "filter[matches.player_ids][overlap]": str(player_id),
                "filter[matches.discipline_id][eq]": _CS2,
                "with": _MATCH_WITH,
            },
        )

    def team_search(self, query: str, *, limit: int = 4) -> Bo3HttpResult:
        return self.request(
            "/filters/teams",
            {
                "page[offset]": 0,
                "page[limit]": limit,
                "filter[teams.discipline_id][eq]": _CS2,
                "search_text": query,
            },
        )
