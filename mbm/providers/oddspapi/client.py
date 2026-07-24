"""Honest OddsPapi HTTP client — query apiKey auth, no browser impersonation."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping

from mbm import __version__

BASE_URL = "https://v5.oddspapi.io/en"
USER_AGENT = f"MBM-esports/{__version__} (+https://github.com/65d9t5sy8w-crypto/MBM-esports)"
CS2_SPORT_ID = 17
API_KEY_ENV = "ODDSPAPI_API_KEY"

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


class OddsPapiClient:
    """Synchronous OddsPapi v5 client using stdlib urllib only."""

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
        return self.request("/sports")

    def tournaments(self, *, sport_id: int = CS2_SPORT_ID) -> OddsPapiHttpResult:
        return self.request("/tournaments", {"sportId": sport_id})

    def fixtures(
        self,
        *,
        sport_id: int = CS2_SPORT_ID,
        tournament_id: int | None = None,
        fixture_ids: str | None = None,
        bookmakers: str | None = None,
    ) -> OddsPapiHttpResult:
        params: dict[str, Any] = {}
        if fixture_ids:
            params["fixtureIds"] = fixture_ids
        else:
            params["sportId"] = sport_id
            if tournament_id is not None:
                params["tournamentId"] = tournament_id
        if bookmakers is not None:
            params["bookmakers"] = bookmakers
        return self.request("/fixtures", params)

    def fixture_odds(
        self,
        fixture_id: str,
        *,
        bookmakers: str | None = "pinnacle",
        main_line: bool | None = True,
    ) -> OddsPapiHttpResult:
        params: dict[str, Any] = {"fixtureId": fixture_id}
        if bookmakers is not None:
            params["bookmakers"] = bookmakers
        if main_line is not None:
            params["mainLine"] = str(main_line).lower()
        return self.request("/fixtures/odds", params)

    def participants(
        self,
        *,
        sport_id: int = CS2_SPORT_ID,
        participant_ids: str | None = None,
    ) -> OddsPapiHttpResult:
        params: dict[str, Any] = {}
        if participant_ids:
            params["participantIds"] = participant_ids
        else:
            params["sportId"] = sport_id
        return self.request("/participants", params)

    def players(
        self,
        *,
        sport_id: int = CS2_SPORT_ID,
        player_ids: str | None = None,
        participant_id: int | None = None,
    ) -> OddsPapiHttpResult:
        params: dict[str, Any] = {}
        if player_ids:
            params["playerIds"] = player_ids
        elif participant_id is not None:
            params["participantId"] = participant_id
        else:
            params["sportId"] = sport_id
        return self.request("/players", params)
