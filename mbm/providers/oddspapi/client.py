"""OddsPapi v4 adapter — authenticated HTTP for verified esports market intake.

Locked production scope (only):
  GET /v4/sports
  GET /v4/tournaments
  GET /v4/odds-by-tournaments

Base host: https://api.oddspapi.io
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from mbm import __version__

BASE_URL = "https://api.oddspapi.io"
USER_AGENT = f"MBM-esports/{__version__} (+https://github.com/65d9t5sy8w-crypto/MBM-esports)"
API_KEY_ENV = "ODDSPAPI_API_KEY"

# Verified esports sport IDs for MBM OddsPapi v4 intake.
SPORT_ID_CS2 = 17
SPORT_ID_LOL = 18
SPORT_ID_VALORANT = 61
VERIFIED_ESPORTS_SPORT_IDS: frozenset[int] = frozenset(
    {SPORT_ID_CS2, SPORT_ID_LOL, SPORT_ID_VALORANT}
)
AUTHORIZED_V4_PATHS: frozenset[str] = frozenset(
    {"/v4/sports", "/v4/tournaments", "/v4/odds-by-tournaments"}
)

_API_KEY_QUERY_RE = re.compile(r"([?&]apiKey=)[^&]*", re.IGNORECASE)


def redact_api_key(url: str) -> str:
    """Strip apiKey values from URLs before logging or raw persistence."""
    return _API_KEY_QUERY_RE.sub(r"\1REDACTED", url)


@dataclass(frozen=True)
class OddsPapiHttpResult:
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


class OddsPapiV4Adapter:
    """Synchronous OddsPapi **v4** adapter using stdlib urllib only.

    Production methods call only the three verified `/v4/` endpoints.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = BASE_URL,
        timeout_s: float = 20.0,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get(API_KEY_ENV, "")
        self.api_key = str(key or "").strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _headers(self) -> dict[str, str]:
        # Honest identity only — no Origin/Referer/sec-ch-ua/Chrome spoofing.
        return {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }

    def request(self, path: str, params: Mapping[str, Any] | None = None) -> OddsPapiHttpResult:
        if path not in AUTHORIZED_V4_PATHS:
            raise ValueError(
                f"OddsPapiV4Adapter refuses unauthorized path {path!r}; "
                "only /v4/sports, /v4/tournaments, /v4/odds-by-tournaments are authorized"
            )
        if not self.api_key:
            return OddsPapiHttpResult(
                ok=False,
                status=0,
                content_type="",
                body=b"",
                url=redact_api_key(f"{self.base_url}{path}"),
                json_body=None,
                unavailable_reason=(
                    f"OddsPapi unavailable: missing apiKey "
                    f"(set {API_KEY_ENV} or pass api_key=)"
                ),
            )

        merged: dict[str, Any] = dict(params or {})
        merged["apiKey"] = self.api_key
        query = urllib.parse.urlencode({k: str(v) for k, v in merged.items()}, doseq=True)
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{query}"
        safe_url = redact_api_key(url)
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                status = int(getattr(resp, "status", 200))
                content_type = resp.headers.get("Content-Type", "")
                body = resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read() if exc.fp is not None else b""
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            return OddsPapiHttpResult(
                ok=False,
                status=int(exc.code),
                content_type=content_type,
                body=body,
                url=safe_url,
                json_body=None,
                unavailable_reason=(
                    f"OddsPapi unavailable: HTTP {exc.code} "
                    f"content_type={content_type or 'missing'}"
                ),
            )
        except TimeoutError as exc:
            return OddsPapiHttpResult(
                ok=False,
                status=0,
                content_type="",
                body=b"",
                url=safe_url,
                json_body=None,
                unavailable_reason=f"OddsPapi unavailable: transport error ({exc})",
            )
        except urllib.error.URLError as exc:
            return OddsPapiHttpResult(
                ok=False,
                status=0,
                content_type="",
                body=b"",
                url=safe_url,
                json_body=None,
                unavailable_reason=f"OddsPapi unavailable: transport error ({exc.reason})",
            )

        if status != 200:
            return OddsPapiHttpResult(
                ok=False,
                status=status,
                content_type=content_type,
                body=body,
                url=safe_url,
                json_body=None,
                unavailable_reason=(
                    f"OddsPapi unavailable: HTTP {status} "
                    f"content_type={content_type or 'missing'}"
                ),
            )
        if not _is_json_content_type(content_type):
            return OddsPapiHttpResult(
                ok=False,
                status=status,
                content_type=content_type,
                body=body,
                url=safe_url,
                json_body=None,
                unavailable_reason=(
                    f"OddsPapi unavailable: HTTP {status} "
                    f"non-JSON content_type={content_type or 'missing'}"
                ),
            )
        try:
            parsed = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            return OddsPapiHttpResult(
                ok=False,
                status=status,
                content_type=content_type,
                body=body,
                url=safe_url,
                json_body=None,
                unavailable_reason=f"OddsPapi unavailable: JSON parse failed ({exc})",
            )
        return OddsPapiHttpResult(
            ok=True,
            status=status,
            content_type=content_type,
            body=body,
            url=safe_url,
            json_body=parsed,
            unavailable_reason=None,
        )

    def sports(self) -> OddsPapiHttpResult:
        return self.request("/v4/sports")

    def tournaments(self, *, sport_id: int) -> OddsPapiHttpResult:
        if sport_id not in VERIFIED_ESPORTS_SPORT_IDS:
            raise ValueError(
                f"sport_id={sport_id} is outside verified MBM esports set "
                f"{sorted(VERIFIED_ESPORTS_SPORT_IDS)}"
            )
        return self.request("/v4/tournaments", {"sportId": sport_id, "language": "en"})

    def odds_by_tournaments(
        self,
        tournament_ids: Sequence[int | str],
        *,
        bookmaker: str = "pinnacle",
        language: str = "en",
        verbosity: int = 3,
        odds_format: str = "decimal",
    ) -> OddsPapiHttpResult:
        ids = [str(t).strip() for t in tournament_ids if str(t).strip()]
        if not ids:
            raise ValueError("odds_by_tournaments requires at least one tournament id")
        params: dict[str, Any] = {
            "tournamentIds": ",".join(ids),
            "language": language,
            "verbosity": verbosity,
            "oddsFormat": odds_format,
        }
        if bookmaker:
            # Verified docs overview uses singular `bookmaker`.
            params["bookmaker"] = bookmaker
        return self.request("/v4/odds-by-tournaments", params)


# Back-compat alias during rename; prefer OddsPapiV4Adapter.
OddsPapiClient = OddsPapiV4Adapter
