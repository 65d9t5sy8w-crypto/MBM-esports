"""PrizePicks capture service — board snapshots only; scoring never touched."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mbm.providers.prizepicks.normalize import (
    SOURCE_BROWSER_BRIDGE,
    SOURCE_LAST_KNOWN_GOOD,
    SOURCE_NONE,
    SOURCE_PROVIDER,
    NormalizedProp,
    normalize_projections_payload,
)
from mbm.providers.prizepicks.sanitize import SensitivePayloadError, reject_sensitive_payload
from mbm.providers.prizepicks.store import SnapshotStore

HEALTH_FIELDS = (
    "ok",
    "source",
    "captured_at",
    "record_count",
    "authoritative_capture",
    "scoring_touched",
    "status",
    "snapshot_id",
)

SCORING_TOUCHED = False


@dataclass
class CaptureResult:
    status: str  # CAPTURED | REJECTED
    cleared_status: str  # CLEARED | NOT_CLEARED
    captured_at: str
    record_count: int
    cleared_count: int
    snapshot_id: str | None
    authoritative_capture: bool
    selected_source: str
    scoring_touched: bool = SCORING_TOUCHED
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "cleared_status": self.cleared_status,
            "captured_at": self.captured_at,
            "record_count": self.record_count,
            "cleared_count": self.cleared_count,
            "snapshot_id": self.snapshot_id,
            "authoritative_capture": self.authoritative_capture,
            "selected_source": self.selected_source,
            "scoring_touched": self.scoring_touched,
            "detail": self.detail,
        }


class PrizePicksCaptureService:
    """Universal PrizePicks capture semantics for the browser bridge."""

    def __init__(self, root: Path, *, bridge_token: str | None = None) -> None:
        self.store = SnapshotStore(root)
        self.bridge_token = bridge_token
        self._provider_valid = False  # server never fetches PrizePicks; provider optional later

    def check_bridge_token(self, header_token: str | None) -> None:
        if self.bridge_token is None:
            return
        if not header_token or header_token != self.bridge_token:
            raise PermissionError("PrizePicks capture requires valid X-MBM-Bridge-Token")

    def capture_board(self, body: dict[str, Any]) -> CaptureResult:
        reject_sensitive_payload(body)

        source = str(body.get("source") or SOURCE_BROWSER_BRIDGE)
        captured_at = str(body.get("captured_at") or "")
        if not captured_at:
            raise ValueError("captured_at is required")

        authoritative = bool(body.get("authoritative_capture", False))
        sports = body.get("sports")
        sports_filter: list[str] | None
        if sports is None:
            sports_filter = None
        elif isinstance(sports, list):
            sports_filter = [str(s).lower() for s in sports]
        else:
            raise ValueError("sports must be a list when provided")

        payload = body.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        reject_sensitive_payload(payload)

        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError("payload.data must be an array")
        # Empty board is a valid capture (zero props); bridge should not call with
        # invalid/non-JSON bodies — those never reach this method.

        records = normalize_projections_payload(
            payload,
            source=source,
            sports_filter=sports_filter,
        )

        envelope = {
            "source": source,
            "captured_at": captured_at,
            "sports": sports_filter,
            "authoritative_capture": authoritative,
            "payload": payload,
            "scoring_touched": SCORING_TOUCHED,
        }
        snap = self.store.append_raw(envelope, captured_at=captured_at)
        self.store.write_normalized(snap.snapshot_id, [r.to_dict() for r in records])

        state = self.store.load_state()
        active: dict[str, Any] = dict(state.get("active_props") or {})
        cleared_count = 0

        for rec in records:
            active[rec.prop_id] = rec.to_dict()

        if authoritative:
            # Removals only for sports in this capture's scope.
            # Full-board (no sports filter) may clear any sport present before.
            scope = set(sports_filter) if sports_filter else None
            captured_ids = {r.prop_id for r in records}
            for prop_id, row in list(active.items()):
                sport = str(row.get("sport") or "unknown")
                if scope is not None and sport not in scope:
                    continue  # scoped capture must never remove other sports
                if prop_id not in captured_ids and row.get("status") != "REMOVED":
                    updated = dict(row)
                    updated["status"] = "REMOVED"
                    active[prop_id] = updated
                    cleared_count += 1

        selected = self._select_source(source, has_records=bool(records) or bool(active))
        state.update(
            {
                "active_props": active,
                "selected_source": selected,
                "last_capture": {
                    "snapshot_id": snap.snapshot_id,
                    "captured_at": captured_at,
                    "record_count": len(records),
                    "authoritative_capture": authoritative,
                    "source": source,
                },
                "last_cleared_at": captured_at if cleared_count else state.get("last_cleared_at"),
                "last_cleared_count": cleared_count
                if cleared_count
                else state.get("last_cleared_count", 0),
            }
        )
        self.store.save_state(state)

        return CaptureResult(
            status="CAPTURED",
            cleared_status="CLEARED" if cleared_count else "NOT_CLEARED",
            captured_at=captured_at,
            record_count=len(records),
            cleared_count=cleared_count,
            snapshot_id=snap.snapshot_id,
            authoritative_capture=authoritative,
            selected_source=selected,
            detail="board snapshot appended",
        )

    def _select_source(self, capture_source: str, *, has_records: bool) -> str:
        """provider valid -> browser bridge -> last-known-good -> none."""
        if self._provider_valid:
            return SOURCE_PROVIDER
        if has_records and capture_source == SOURCE_BROWSER_BRIDGE:
            return SOURCE_BROWSER_BRIDGE
        state = self.store.load_state()
        if state.get("active_props"):
            return SOURCE_LAST_KNOWN_GOOD
        if has_records:
            return capture_source or SOURCE_BROWSER_BRIDGE
        return SOURCE_NONE

    def latest_snapshot(self) -> dict[str, Any]:
        latest = self.store.latest_snapshot()
        state = self.store.load_state()
        return {
            "snapshot": latest,
            "selected_source": state.get("selected_source", SOURCE_NONE),
            "active_prop_count": len(
                [p for p in (state.get("active_props") or {}).values() if p.get("status") != "REMOVED"]
            ),
            "scoring_touched": SCORING_TOUCHED,
        }

    def board_history(self) -> dict[str, Any]:
        ids = self.store.list_snapshot_ids()
        return {
            "snapshots": ids,
            "count": len(ids),
            "scoring_touched": SCORING_TOUCHED,
        }

    def health(self) -> dict[str, Any]:
        state = self.store.load_state()
        last = state.get("last_capture") or {}
        active = [
            p
            for p in (state.get("active_props") or {}).values()
            if p.get("status") != "REMOVED"
        ]
        body = {
            "ok": True,
            "source": state.get("selected_source", SOURCE_NONE),
            "captured_at": last.get("captured_at"),
            "record_count": len(active),
            "authoritative_capture": bool(last.get("authoritative_capture", False)),
            "scoring_touched": SCORING_TOUCHED,
            "status": "CAPTURED" if last else "NONE",
            "snapshot_id": last.get("snapshot_id"),
        }
        # Exactly the eight allowlisted fields.
        return {k: body[k] for k in HEALTH_FIELDS}

    def active_props(self) -> list[NormalizedProp]:
        state = self.store.load_state()
        out: list[NormalizedProp] = []
        for row in (state.get("active_props") or {}).values():
            out.append(
                NormalizedProp(
                    prop_id=str(row["prop_id"]),
                    player_id=str(row.get("player_id") or ""),
                    player_name=str(row.get("player_name") or ""),
                    team=str(row.get("team") or ""),
                    league=str(row.get("league") or ""),
                    sport=str(row.get("sport") or "unknown"),
                    stat=str(row.get("stat") or ""),
                    line=row.get("line"),
                    start_time=row.get("start_time"),
                    identity_status=str(row.get("identity_status") or "unresolved"),
                    status=str(row.get("status") or "ACTIVE"),
                    source=str(row.get("source") or SOURCE_BROWSER_BRIDGE),
                )
            )
        return out


__all__ = [
    "CaptureResult",
    "HEALTH_FIELDS",
    "PrizePicksCaptureService",
    "SCORING_TOUCHED",
    "SensitivePayloadError",
]
