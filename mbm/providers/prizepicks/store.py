"""Append-only PrizePicks board snapshot store."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class SnapshotRef:
    snapshot_id: str
    path: Path
    captured_at: str


class SnapshotStore:
    """Immutable append-only snapshots under root/snapshots/."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.snapshots_dir = self.root / "snapshots"
        self.normalized_dir = self.root / "normalized"
        self.state_path = self.root / "board_state.json"
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.normalized_dir.mkdir(parents=True, exist_ok=True)

    def append_raw(
        self,
        envelope: dict[str, Any],
        *,
        captured_at: str | None = None,
    ) -> SnapshotRef:
        ts = captured_at or str(envelope.get("captured_at") or _iso_now())
        # Unique id: timestamp + monotonic sequence among same-second writes.
        existing = list(self.snapshots_dir.glob(f"{ts.replace(':', '')}*"))
        seq = len(existing)
        safe_ts = ts.replace(":", "").replace("-", "")
        snapshot_id = f"{safe_ts}-{seq:04d}"
        path = self.snapshots_dir / f"{snapshot_id}.json"
        if path.exists():
            raise ValueError(f"raw snapshot is append-only: refusing overwrite of {path}")
        path.write_text(json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8")
        return SnapshotRef(snapshot_id=snapshot_id, path=path, captured_at=ts)

    def write_normalized(self, snapshot_id: str, records: list[dict[str, Any]]) -> Path:
        path = self.normalized_dir / f"{snapshot_id}.json"
        if path.exists():
            raise ValueError(f"normalized snapshot is append-only: refusing overwrite of {path}")
        path.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def list_snapshot_ids(self) -> list[str]:
        ids = sorted(p.stem for p in self.snapshots_dir.glob("*.json"))
        return ids

    def read_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        path = self.snapshots_dir / f"{snapshot_id}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def latest_snapshot(self) -> dict[str, Any] | None:
        ids = self.list_snapshot_ids()
        if not ids:
            return None
        return self.read_snapshot(ids[-1])

    def load_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {
                "active_props": {},
                "selected_source": "none",
                "last_capture": None,
                "last_cleared_at": None,
                "last_cleared_count": 0,
            }
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def save_state(self, state: dict[str, Any]) -> None:
        self.state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
