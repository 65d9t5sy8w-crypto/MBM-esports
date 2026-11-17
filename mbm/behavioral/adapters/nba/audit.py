"""Audit control for NBA backtest / walk-forward results.

Every reported result must preserve enough provenance to reproduce the row
independently: prediction timestamp, model version, source snapshot IDs,
sportsbook price, and settlement outcome.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


MODEL_VERSION = "nba-mbm-walkforward-0.1.0"


@dataclass(frozen=True)
class SportsbookPriceAudit:
    vendor: str
    line: float
    more_odds: int | None
    less_odds: int | None
    captured_at: str
    raw_evidence_ref: str


@dataclass(frozen=True)
class BacktestAuditRecord:
    """Immutable audit row attached to each walk-forward prediction result."""

    prediction_timestamp: str
    model_version: str
    game_id: str
    cutoff_as_of: str
    source_snapshot_identifiers: tuple[str, ...]
    sportsbook_price: SportsbookPriceAudit | None
    settlement_outcome: str | None  # more | less | push | pending | unavailable
    settlement_value: float | None
    action: str
    p_more: float
    fold_index: int
    train_game_ids: tuple[str, ...]
    purged_train_keys: tuple[str, ...]
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload

    def missing_audit_fields(self) -> tuple[str, ...]:
        missing: list[str] = []
        if not self.prediction_timestamp:
            missing.append("prediction_timestamp")
        if not self.model_version:
            missing.append("model_version")
        if not self.source_snapshot_identifiers:
            missing.append("source_snapshot_identifiers")
        if self.sportsbook_price is None:
            missing.append("sportsbook_price")
        if self.settlement_outcome is None:
            missing.append("settlement_outcome")
        return tuple(missing)


def require_complete_audit(record: BacktestAuditRecord) -> None:
    missing = record.missing_audit_fields()
    if missing:
        raise ValueError(
            "backtest audit incomplete — cannot report result without "
            + ", ".join(missing)
        )


def build_audit_record(
    *,
    prediction_timestamp: str,
    game_id: str,
    cutoff_as_of: str,
    source_snapshot_identifiers: tuple[str, ...] | list[str],
    sportsbook_price: SportsbookPriceAudit | None,
    settlement_outcome: str | None,
    settlement_value: float | None,
    action: str,
    p_more: float,
    fold_index: int,
    train_game_ids: tuple[str, ...] | list[str],
    purged_train_keys: tuple[str, ...] | list[str],
    model_version: str = MODEL_VERSION,
    extra: dict[str, Any] | None = None,
    require_complete: bool = True,
) -> BacktestAuditRecord:
    record = BacktestAuditRecord(
        prediction_timestamp=prediction_timestamp,
        model_version=model_version,
        game_id=str(game_id),
        cutoff_as_of=cutoff_as_of,
        source_snapshot_identifiers=tuple(source_snapshot_identifiers),
        sportsbook_price=sportsbook_price,
        settlement_outcome=settlement_outcome,
        settlement_value=settlement_value,
        action=action,
        p_more=float(p_more),
        fold_index=int(fold_index),
        train_game_ids=tuple(train_game_ids),
        purged_train_keys=tuple(purged_train_keys),
        extra=dict(extra or {}),
    )
    if require_complete:
        require_complete_audit(record)
    return record
