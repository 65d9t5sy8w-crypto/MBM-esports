"""Settlement monitor rows from recorded fixture JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mbm.analyst.models import SettlementRow


def load_settlement(path: Path, *, pick_id: str, event_id: str, data_label: str) -> SettlementRow:
    if not path.is_file():
        return SettlementRow(
            pick_id=pick_id,
            event_id=event_id,
            status="unavailable",
            recorded_result=None,
            outcome="unavailable",
            source="none",
            captured_at="",
            data_label=data_label,
        )
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    status = str(payload.get("status", "unavailable"))
    result = payload.get("recorded_result")
    outcome = str(payload.get("outcome", status))
    return SettlementRow(
        pick_id=pick_id,
        event_id=event_id,
        status=status,
        recorded_result=float(result) if result is not None else None,
        outcome=outcome,
        source=str(payload.get("source", "manual-fixture-drop")),
        captured_at=str(payload.get("captured_at", "")),
        data_label=data_label,
    )
