"""Immutable raw evidence store. Raw bytes are never mutated after write."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RawRecord:
    content_hash: str
    path: Path
    media_type: str


class RawStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        event_id: str,
        payload: bytes | str | dict[str, Any],
        *,
        filename: str = "payload.json",
        media_type: str = "application/json",
    ) -> RawRecord:
        if isinstance(payload, dict):
            data = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
            media_type = "application/json"
        elif isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = payload

        digest = hashlib.sha256(data).hexdigest()
        dest_dir = self.root / event_id / "raw"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        if dest.exists():
            existing = dest.read_bytes()
            if existing != data:
                raise ValueError(
                    f"raw evidence is immutable: refusing overwrite of {dest} "
                    f"(hash mismatch with existing content)"
                )
        else:
            dest.write_bytes(data)
        return RawRecord(content_hash=digest, path=dest, media_type=media_type)

    def read_bytes(self, event_id: str, filename: str = "payload.json") -> bytes:
        path = self.root / event_id / "raw" / filename
        return path.read_bytes()

    def read_json(self, event_id: str, filename: str = "payload.json") -> dict[str, Any]:
        return json.loads(self.read_bytes(event_id, filename).decode("utf-8"))
