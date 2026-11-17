"""BallDontLie NBA refresh pipeline: live raw only for verified FREE endpoints."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mbm.intake.raw.store import RawStore
from mbm.intake.types import EvidenceEnvelope
from mbm.providers.balldontlie.client import (
    BallDontLieHttpResult,
    BallDontLieNbaAdapter,
    redact_url,
)
from mbm.providers.balldontlie.normalize import (
    SOURCE_BALLDONTLIE,
    SOURCE_SYNTHETIC,
    normalize_balldontlie_bundle,
    unavailable_envelope,
)

SYNTHETIC_SOURCE = SOURCE_SYNTHETIC


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _meta(result: BallDontLieHttpResult, endpoint: str) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "path": result.path,
        "url": redact_url(result.url),
        "status": result.status,
        "content_type": result.content_type,
        "unavailable_reason": result.unavailable_reason,
        "enabled": result.enabled,
    }


def _write_live_raw(store: RawStore, event_key: str, name: str, result: BallDontLieHttpResult) -> str:
    meta_name = f"{name}.meta.json"
    body_name = f"{name}.body"
    store.write(
        event_key,
        {
            "source": SOURCE_BALLDONTLIE,
            "captured_at": _iso_now(),
            "url": redact_url(result.url),
            "path": result.path,
            "status": result.status,
            "content_type": result.content_type,
            "unavailable_reason": result.unavailable_reason,
            "enabled": result.enabled,
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
    prop_stat: str = "points",
) -> EvidenceEnvelope:
    """Build envelope from hand-authored synthetic fixtures (unit tests only)."""
    bundle: dict[str, Any] = {
        "source": SYNTHETIC_SOURCE,
        "captured_at": None,
        "not_for_projection": True,
        "http_meta": [],
    }
    mapping = {
        "teams.json": "teams",
        "players.json": "players",
        "games.json": "games",
        "stats.json": "stats",
        "advanced_stats.json": "advanced_stats",
        "injuries.json": "injuries",
        "lineups.json": "lineups",
        "projected_lineups.json": "projected_lineups",
        "odds.json": "odds",
        "player_props.json": "player_props",
    }
    for filename, key in mapping.items():
        path = synthetic_dir / filename
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = payload.get("_fixture_meta") if isinstance(payload, dict) else None
        if not isinstance(meta, dict) or meta.get("source") != SYNTHETIC_SOURCE:
            raise ValueError(
                f"{path} must declare _fixture_meta.source={SYNTHETIC_SOURCE!r} "
                "(hand-authored fixtures must not be labeled as BallDontLie recorded evidence)"
            )
        if meta.get("not_for_projection") is not True:
            raise ValueError(f"{path} must set not_for_projection=true")
        if meta.get("captured_at") is not None:
            raise ValueError(f"{path} synthetic captured_at must be null")

        body = _strip_fixture_meta(payload)
        if isinstance(body, dict) and "status" in body and "body" in body and "content_type" in body:
            status = int(body.get("status") or 0)
            content_type = str(body.get("content_type") or "")
            reason = body.get("unavailable_reason") or (
                f"BallDontLie unavailable: HTTP {status} content_type={content_type or 'missing'}"
            )
            bundle["http_meta"].append(
                {
                    "endpoint": key,
                    "url": body.get("url"),
                    "status": status,
                    "content_type": content_type,
                    "unavailable_reason": reason,
                    "enabled": body.get("enabled", False),
                    "synthetic": True,
                }
            )
            continue

        if isinstance(body, dict) and "data" in body:
            body = body["data"]

        bundle["http_meta"].append(
            {
                "endpoint": key,
                "status": 200,
                "content_type": "application/json",
                "unavailable_reason": None,
                "enabled": True,
                "synthetic": True,
            }
        )
        bundle[key] = body

    env = normalize_balldontlie_bundle(
        bundle,
        captured_at="1970-01-01T00:00:00Z",
        raw_ref=None,
        target_player_id=target_player_id,
        line=line,
        prop_stat=prop_stat,
        force_source=SYNTHETIC_SOURCE,
        not_for_projection=True,
    )
    if out_dir is not None:
        dest = out_dir / "synthetic_out" / env.fixture.event_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "normalized.json").write_text(
            json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
        )
    return env


def refresh_live_smoke(
    client: BallDontLieNbaAdapter,
    *,
    out_dir: Path,
    seasons: list[int] | None = None,
    per_page: int = 5,
) -> EvidenceEnvelope:
    """One-shot live smoke against verified FREE BallDontLie endpoints only.

    Does not call paid endpoints. Requires BALLDONTLIE_API_KEY.
    """
    captured = _iso_now()
    store = RawStore(out_dir / "balldontlie")
    event_key = f"live-{captured.replace(':', '').replace('-', '')}"
    bundle: dict[str, Any] = {
        "source": SOURCE_BALLDONTLIE,
        "captured_at": captured,
        "not_for_projection": False,
        "http_meta": [],
    }
    seasons = seasons or [2025]

    teams = client.teams()
    bundle["http_meta"].append(_meta(teams, "teams"))
    _write_live_raw(store, event_key, "teams", teams)
    if teams.available:
        bundle["teams"] = teams.json_body

    players = client.players(per_page=per_page)
    bundle["http_meta"].append(_meta(players, "players"))
    _write_live_raw(store, event_key, "players", players)
    if players.available:
        bundle["players"] = players.json_body

    games = client.games(per_page=per_page, **{"seasons[]": seasons})
    bundle["http_meta"].append(_meta(games, "games"))
    _write_live_raw(store, event_key, "games", games)
    if not games.available:
        assert games.unavailable_reason is not None
        env = unavailable_envelope(
            games.unavailable_reason,
            captured_at=captured,
            raw_ref=str((out_dir / "balldontlie" / event_key / "raw" / "games.body").as_posix()),
        )
        dest = out_dir / env.fixture.event_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "normalized.json").write_text(
            json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        return env

    bundle["games"] = games.json_body

    # Explicitly record that paid endpoints were not called (disabled).
    for paid in (
        "stats",
        "player_injuries",
        "advanced_stats",
        "odds",
        "player_props",
        "lineups",
        "projected_lineups",
    ):
        result = getattr(client, paid)()
        bundle["http_meta"].append(_meta(result, paid))
        # Do not persist paid probe bodies by default (disabled, no network).

    raw = store.write(event_key, bundle, filename="bundle.json")
    env = normalize_balldontlie_bundle(
        bundle,
        captured_at=captured,
        raw_ref=str(raw.path.as_posix()),
        force_source=SOURCE_BALLDONTLIE,
        not_for_projection=False,
    )
    dest = out_dir / env.fixture.event_id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "normalized.json").write_text(
        json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
    )
    return env
