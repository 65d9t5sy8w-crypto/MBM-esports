"""OddsPapi v4 refresh pipeline: live raw only for verified /v4 endpoints."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from mbm.intake.raw.store import RawStore
from mbm.intake.types import EvidenceEnvelope
from mbm.providers.oddspapi.client import (
    SPORT_ID_CS2,
    OddsPapiHttpResult,
    OddsPapiV4Adapter,
    redact_api_key,
)
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
    """Persist live OddsPapi v4 response bytes under intake/raw/oddspapi.

    Stores the original ``result.body`` bytes (plus redacted metadata) so
    provider formatting/key order survive for provenance hashing. Does not
    re-serialize ``json_body``.
    """
    meta_name = f"{name}.meta.json"
    body_name = f"{name}.body"
    store.write(
        event_key,
        {
            "source": ODDSPAPI_SOURCE,
            "captured_at": _iso_now(),
            "url": redact_api_key(result.url),
            "status": result.status,
            "content_type": result.content_type,
            "unavailable_reason": result.unavailable_reason,
            "body_filename": body_name,
            "body_sha256": hashlib.sha256(result.body).hexdigest(),
            "body_byte_length": len(result.body),
        },
        filename=meta_name,
    )
    record = store.write(
        event_key,
        result.body,
        filename=body_name,
        media_type=result.content_type or "application/octet-stream",
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
    sport_id: int | None = None,
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
        "odds_by_tournaments.json": "odds_by_tournaments",
    }
    for filename, key in mapping.items():
        path = synthetic_dir / filename
        if not path.is_file():
            if key == "odds_by_tournaments":
                bundle["http_meta"].append(
                    {
                        "endpoint": key,
                        "status": 0,
                        "content_type": "",
                        "unavailable_reason": (
                            f"synthetic fixture missing ({filename}); "
                            "not an OddsPapi v4 response"
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
        # Synthetic HTTP-wrapper failure case (e.g. 401 on v4).
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

        # sports/tournaments may be a bare array at top level after meta strip,
        # or wrapped {"results": [...]} / single object.
        if key in {"sports", "tournaments", "odds_by_tournaments"} and isinstance(body, dict):
            if "results" in body:
                body = body["results"]
            elif key == "sports" and "sportId" in body:
                body = [body]

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
        sport_id=sport_id,
    )
    if out_dir is not None:
        dest = out_dir / "synthetic_out" / env.fixture.event_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "normalized.json").write_text(
            json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
        )
    return env


def _tournament_ids_from_payload(payload: Any, *, limit: int = 5) -> list[str]:
    ids: list[str] = []
    rows = payload if isinstance(payload, list) else []
    if isinstance(payload, dict):
        rows = payload.get("results") or payload.get("data") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tid = row.get("tournamentId") or row.get("id")
        if tid is None:
            continue
        ids.append(str(tid))
        if len(ids) >= limit:
            break
    return ids


def refresh_live_smoke(
    client: OddsPapiV4Adapter,
    *,
    out_dir: Path,
    sport_id: int = SPORT_ID_CS2,
    tournament_ids: Sequence[int | str] | None = None,
    bookmaker: str = "pinnacle",
) -> EvidenceEnvelope:
    """One-shot live smoke against OddsPapi **v4**. No browser impersonation. No retries.

    Requires apiKey via client / ODDSPAPI_API_KEY. Calls only:
      /v4/sports, /v4/tournaments, /v4/odds-by-tournaments
    """
    captured = _iso_now()
    store = RawStore(out_dir / "oddspapi")
    event_key = f"live-{captured.replace(':', '').replace('-', '')}"
    bundle: dict[str, Any] = {
        "source": ODDSPAPI_SOURCE,
        "captured_at": captured,
        "not_for_projection": False,
        "sport_id": sport_id,
        "http_meta": [],
    }

    sports = client.sports()
    bundle["http_meta"].append(_meta(sports, "sports"))
    _write_live_raw(store, event_key, "sports", sports)
    if sports.available:
        bundle["sports"] = sports.json_body

    tournaments = client.tournaments(sport_id=sport_id)
    bundle["http_meta"].append(_meta(tournaments, "tournaments"))
    _write_live_raw(store, event_key, "tournaments", tournaments)
    if not tournaments.available:
        assert tournaments.unavailable_reason is not None
        env = unavailable_envelope(
            tournaments.unavailable_reason,
            captured_at=captured,
            raw_ref=str(
                (out_dir / "oddspapi" / event_key / "raw" / "tournaments.body").as_posix()
            ),
        )
        dest = out_dir / env.fixture.event_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "normalized.json").write_text(
            json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        return env

    bundle["tournaments"] = tournaments.json_body
    ids = [str(t) for t in tournament_ids] if tournament_ids else _tournament_ids_from_payload(
        tournaments.json_body
    )
    if not ids:
        env = unavailable_envelope(
            "OddsPapi unavailable: tournaments response contained no tournamentId values",
            captured_at=captured,
        )
        dest = out_dir / env.fixture.event_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "normalized.json").write_text(
            json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        return env

    odds = client.odds_by_tournaments(ids, bookmaker=bookmaker)
    bundle["http_meta"].append(_meta(odds, "odds_by_tournaments"))
    _write_live_raw(store, event_key, "odds_by_tournaments", odds)
    if not odds.available:
        assert odds.unavailable_reason is not None
        env = unavailable_envelope(
            odds.unavailable_reason,
            captured_at=captured,
            raw_ref=str(
                (
                    out_dir / "oddspapi" / event_key / "raw" / "odds_by_tournaments.body"
                ).as_posix()
            ),
        )
        dest = out_dir / env.fixture.event_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "normalized.json").write_text(
            json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        return env

    bundle["odds_by_tournaments"] = odds.json_body
    raw = store.write(event_key, bundle, filename="bundle.json")
    env = normalize_oddspapi_bundle(
        bundle,
        captured_at=captured,
        raw_ref=str(raw.path.as_posix()),
        force_source=ODDSPAPI_SOURCE,
        not_for_projection=False,
        sport_id=sport_id,
    )
    dest = out_dir / env.fixture.event_id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "normalized.json").write_text(
        json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
    )
    return env
