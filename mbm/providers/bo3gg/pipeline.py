"""BO3 refresh pipeline: preserve raw only for live BO3; synthetic stays labeled."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mbm.intake.raw.store import RawStore
from mbm.intake.types import EvidenceEnvelope, ProvenanceItem, SourceAttempt
from mbm.providers.bo3gg.client import Bo3Client, Bo3HttpResult
from mbm.providers.bo3gg.normalize import normalize_bo3_bundle, unavailable_envelope

SYNTHETIC_SOURCE = "synthetic_test_fixture"
BO3_SOURCE = "bo3.gg"


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _meta(result: Bo3HttpResult, endpoint: str) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "url": result.url,
        "status": result.status,
        "content_type": result.content_type,
        "unavailable_reason": result.unavailable_reason,
    }


def _write_live_raw(store: RawStore, event_key: str, name: str, result: Bo3HttpResult) -> str:
    """Persist byte-for-byte live BO3 outcome under intake/raw/bo3gg only."""
    record = store.write(
        event_key,
        {
            "source": BO3_SOURCE,
            "captured_at": _iso_now(),
            "url": result.url,
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

    Never labels the envelope as bo3.gg provider evidence.
    """
    bundle: dict[str, Any] = {
        "source": SYNTHETIC_SOURCE,
        "captured_at": None,
        "not_for_projection": True,
        "http_meta": [],
    }
    mapping = {
        "upcoming.json": "upcoming",
        "live.json": "live",
        "finished.json": "finished",
        "match_detail.json": "match_detail",
        "player_history.json": "player_history",
        "team_search.json": "team_search",
    }
    for filename, key in mapping.items():
        path = synthetic_dir / filename
        if not path.is_file():
            bundle["http_meta"].append(
                {
                    "endpoint": key,
                    "status": 0,
                    "content_type": "",
                    "unavailable_reason": (
                        f"synthetic fixture missing ({filename}); not a BO3.gg response"
                    ),
                }
            )
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        meta = payload.get("_fixture_meta") if isinstance(payload, dict) else None
        if not isinstance(meta, dict) or meta.get("source") != SYNTHETIC_SOURCE:
            raise ValueError(
                f"{path} must declare _fixture_meta.source={SYNTHETIC_SOURCE!r} "
                "(hand-authored fixtures must not be labeled as BO3 recorded evidence)"
            )
        if meta.get("not_for_projection") is not True:
            raise ValueError(f"{path} must set not_for_projection=true")
        if meta.get("captured_at") is not None:
            raise ValueError(f"{path} synthetic captured_at must be null")

        body = _strip_fixture_meta(payload)
        # Synthetic HTTP-wrapper failure case (e.g. 403).
        if isinstance(body, dict) and "status" in body and "body" in body and "content_type" in body:
            status = int(body.get("status") or 0)
            content_type = str(body.get("content_type") or "")
            reason = body.get("unavailable_reason") or (
                f"BO3 unavailable: HTTP {status} content_type={content_type or 'missing'}"
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

    # Normalize using a synthetic clock for tests when success path needs a timestamp.
    # Envelope source remains synthetic_test_fixture — never bo3.gg.
    env = normalize_bo3_bundle(
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


# Back-compat alias name used during early draft — points at synthetic path only.
refresh_from_recorded = refresh_from_synthetic


def refresh_live_smoke(
    client: Bo3Client,
    *,
    out_dir: Path,
    team_query: str | None = None,
) -> EvidenceEnvelope:
    """One-shot live smoke against BO3.gg. No browser impersonation. No retries.

    Live raw bytes go under out_dir (intended: intake/raw/bo3gg or fixtures only after
    a real response). Failures become explicit BO3 unavailable PASS reasons.
    """
    captured = _iso_now()
    store = RawStore(out_dir / "bo3gg")
    event_key = f"live-{captured.replace(':', '').replace('-', '')}"
    bundle: dict[str, Any] = {
        "source": BO3_SOURCE,
        "captured_at": captured,
        "not_for_projection": False,
        "http_meta": [],
    }

    upcoming = client.upcoming_matches(limit=5)
    bundle["http_meta"].append(_meta(upcoming, "upcoming"))
    _write_live_raw(store, event_key, "upcoming", upcoming)
    if not upcoming.available:
        assert upcoming.unavailable_reason is not None
        env = unavailable_envelope(
            upcoming.unavailable_reason,
            captured_at=captured,
            raw_ref=str((out_dir / "bo3gg" / event_key / "raw" / "upcoming.json").as_posix()),
        )
        dest = out_dir / env.fixture.event_id
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "normalized.json").write_text(
            json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        return env

    bundle["upcoming"] = upcoming.json_body

    live = client.live_matches(limit=5)
    bundle["http_meta"].append(_meta(live, "live"))
    _write_live_raw(store, event_key, "live", live)
    if live.available:
        bundle["live"] = live.json_body

    finished = client.finished_matches(limit=5)
    bundle["http_meta"].append(_meta(finished, "finished"))
    _write_live_raw(store, event_key, "finished", finished)
    if finished.available:
        bundle["finished"] = finished.json_body

    results = upcoming.json_body
    first = None
    if isinstance(results, dict):
        arr = results.get("results") or results.get("data") or []
        if isinstance(arr, list) and arr:
            first = arr[0]
    elif isinstance(results, list) and results:
        first = results[0]
    if isinstance(first, dict) and first.get("slug"):
        detail = client.match_detail(str(first["slug"]))
        bundle["http_meta"].append(_meta(detail, "match_detail"))
        _write_live_raw(store, event_key, "match_detail", detail)
        if detail.available:
            bundle["match_detail"] = detail.json_body

    if team_query:
        search = client.team_search(team_query)
        bundle["http_meta"].append(_meta(search, "team_search"))
        _write_live_raw(store, event_key, "team_search", search)
        if search.available:
            bundle["team_search"] = search.json_body

    raw = store.write(event_key, bundle, filename="bundle.json")
    env = normalize_bo3_bundle(
        bundle,
        captured_at=captured,
        raw_ref=str(raw.path.as_posix()),
        force_source=BO3_SOURCE,
        not_for_projection=False,
    )
    dest = out_dir / env.fixture.event_id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "normalized.json").write_text(
        json.dumps(env.to_dict(), indent=2, default=str), encoding="utf-8"
    )
    return env
