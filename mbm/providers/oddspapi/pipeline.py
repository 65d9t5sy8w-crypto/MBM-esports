"""OddsPapi refresh pipeline: preserve raw only for live calls; synthetic stays labeled."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mbm.intake.raw.store import RawStore
from mbm.intake.types import EvidenceEnvelope
from mbm.providers.oddspapi.client import OddsPapiClient, OddsPapiHttpResult, redact_api_key
from mbm.providers.oddspapi.normalize import normalize_oddspapi_bundle, unavailable_envelope

SYNTHETIC_SOURCE = "synthetic_test_fixture"
ODDSPAPI_SOURCE = "oddspapi"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _meta(result: OddsPapiHttpResult, endpoint: str) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "url": redact_api_key(result.url),
        "status": result.status,
        "content_type": result.content_type,
        "unavailable_reason": result.unavailable_reason,
    }


def _write_live_raw(store: RawStore, event_key: str, name: str, result: OddsPapiHttpResult) -> str:
    """Persist byte-for-byte live OddsPapi outcome under intake/raw/oddspapi only."""
    record = store.write(
        event_key,
        {
            "source": ODDSPAPI_SOURCE,
            "captured_at": _iso_now(),
            "url": redact_api_key(result.url),
            "status": result.status,
            "content_type": result.content_type,
            "unavailable_reason": result.unavailable_reason,
            "body": result.json_body
            if result.json_body is not None
            else result.body.decode("utf-8", errors="replace"),
        },
        filename=f"{name}.json",
    )
    return str(record.path.as_posix())


def _strip_fixture_meta(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: v for k, v in payload.items() if k != "_fixture_meta"}
    return payload


def refresh_from_synthetic(
    synthetic_dir: Path,
    *,
    out_dir: Path | None = None,
    target_player_id: str | None = None,
    line: float | None = None,
) -> EvidenceEnvelope:
    """Build envelope from hand-authored synthetic fixtures (unit tests only).

    Never labels the envelope as oddspapi provider evidence.
    """
    bundle: dict[str, Any] = {
        "source": SYNTHETIC_SOURCE,
        "captured_at": None,
        "not_for_projection": True,
        "http_meta": [],
    }
    mapping = {
        "sports.json": "sports",
        "tournaments.json": "tournaments",
        "fixtures.json": "fixtures",
        "fixture_odds.json": "fixture_odds",
        "participants.json": "participants",
        "players.json": "players",
        "markets.json": "markets",
    }
    for filename, key in mapping.items():
        path = synthetic_dir / filename
        if not path.is_file():
            # Optional endpoints may be absent; only fixtures/odds are critical.
            if key in {"fixtures", "fixture_odds"}:
                bundle["http_meta"].append(
                    {
                        "endpoint": key,
                        "status": 0,
                        "content_type": "",
                        "unavailable_reason": (
                            f"synthetic fixture missing ({filename}); "
                            "not an OddsPapi response"
                        ),
                    }
                )
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = payload.get("_fixture_meta") if isinstance(payload, dict) else None
        if not isinstance(meta, dict) or meta.get("source") != SYNTHETIC_SOURCE:
            raise ValueError(
                f"{path} must declare _fixture_meta.source={SYNTHETIC_SOURCE!r} "
                "(hand-authored fixtures must not be labeled as OddsPapi recorded evidence)"
            )
        if meta.get("not_for_projection") is not True:
            raise ValueError(f"{path} must set not_for_projection=true")
        if meta.get("captured_at") is not None:
            raise ValueError(f"{path} synthetic captured_at must be null")

        body = _strip_fixture_meta(payload)
        # Synthetic HTTP-wrapper failure case (e.g. 401).
        if isinstance(body, dict) and "status" in body and "body" in body and "content_type" in body:
            status = int(body.get("status") or 0)
            content_type = str(body.get("content_type") or "")
            reason = body.get("unavailable_reason") or (
                f"OddsPapi unavailable: HTTP {status} content_type={content_type or 'missing'}"
            )
            bundle["http_meta"].append(
                {
                    "endpoint": key,
                    "url": body.get("url"),
                    "status": status,
                    "content_type": content_type,
                    "unavailable_reason": reason,
                    "synthetic": True,
                }
            )
            continue

        bundle["http_meta"].append(
            {
                "endpoint": key,
                "status": 200,
                "content_type": "application/json",
                "unavailable_reason": None,
                "synthetic": True,
            }
        )
        bundle[key] = body

    env = normalize_oddspapi_bundle(
        bundle,
        captured_at="1970-01-01T00:00:00Z",
        raw_ref=None,
        target_player_id=target_player_id,
        line=line,
        force_source=SYNTHETIC_SOURCE,
        not_for_projection=True,
        captured_at_display=None,
    )
    if out_dir is not None:
        dest = out_dir / "synthetic_out" / env.fixture.event_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "normalized.json").write_text(
            json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
        )
    return env


def refresh_live_smoke(
    client: OddsPapiClient,
    *,
    out_dir: Path,
    tournament_id: int | None = None,
    bookmakers: str = "pinnacle",
) -> EvidenceEnvelope:
    """One-shot live smoke against OddsPapi v5. No browser impersonation. No retries.

    Requires apiKey via client / ODDSPAPI_API_KEY. Live raw bytes go under out_dir
    (intended: intake/raw/oddspapi). Failures become explicit OddsPapi unavailable
    PASS reasons. API keys are redacted from stored URLs.
    """
    captured = _iso_now()
    store = RawStore(out_dir / "oddspapi")
    event_key = f"live-{captured.replace(':', '').replace('-', '')}"
    bundle: dict[str, Any] = {
        "source": ODDSPAPI_SOURCE,
        "captured_at": captured,
        "not_for_projection": False,
        "http_meta": [],
    }

    tournaments = client.tournaments()
    bundle["http_meta"].append(_meta(tournaments, "tournaments"))
    _write_live_raw(store, event_key, "tournaments", tournaments)
    if tournaments.available:
        bundle["tournaments"] = tournaments.json_body

    fixtures = client.fixtures(tournament_id=tournament_id, bookmakers=bookmakers)
    bundle["http_meta"].append(_meta(fixtures, "fixtures"))
    _write_live_raw(store, event_key, "fixtures", fixtures)
    if not fixtures.available:
        assert fixtures.unavailable_reason is not None
        env = unavailable_envelope(
            fixtures.unavailable_reason,
            captured_at=captured,
            raw_ref=str((out_dir / "oddspapi" / event_key / "raw" / "fixtures.json").as_posix()),
        )
        dest = out_dir / env.fixture.event_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "normalized.json").write_text(
            json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        return env

    bundle["fixtures"] = fixtures.json_body
    rows = fixtures.json_body if isinstance(fixtures.json_body, list) else []
    first = rows[0] if rows and isinstance(rows[0], dict) else None
    if first is None and isinstance(fixtures.json_body, dict):
        arr = fixtures.json_body.get("data") or fixtures.json_body.get("fixtures") or []
        if isinstance(arr, list) and arr and isinstance(arr[0], dict):
            first = arr[0]

    if isinstance(first, dict) and first.get("fixtureId"):
        odds = client.fixture_odds(str(first["fixtureId"]), bookmakers=bookmakers)
        bundle["http_meta"].append(_meta(odds, "fixture_odds"))
        _write_live_raw(store, event_key, "fixture_odds", odds)
        if odds.available:
            bundle["fixture_odds"] = odds.json_body

    raw = store.write(event_key, bundle, filename="bundle.json")
    env = normalize_oddspapi_bundle(
        bundle,
        captured_at=captured,
        raw_ref=str(raw.path.as_posix()),
        force_source=ODDSPAPI_SOURCE,
        not_for_projection=False,
    )
    dest = out_dir / env.fixture.event_id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "normalized.json").write_text(
        json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
    )
    return env
