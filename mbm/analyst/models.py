"""Canonical analyst view models (intake/evidence only — no adapter types)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class GateView:
    name: str
    passed: bool
    detail: str
    value: float | None = None


@dataclass(frozen=True)
class BoardRow:
    pick_id: str
    event_id: str
    team_a: str
    team_b: str
    start_time: str
    market_scope: str
    player_id: str
    player_name: str
    stat: str
    line: float
    recommendation: str
    grade: str
    probability: float
    eligible: bool
    eligibility_reason: str
    evidence_status: str
    last_refresh: str
    data_label: str  # e.g. fixture/demo


@dataclass(frozen=True)
class PickDetail:
    pick_id: str
    board: BoardRow
    identity_status: str
    identity_notes: list[str]
    source_attempts: list[dict[str, str]]
    raw_refs: list[str]
    map_context: dict[str, Any]
    opportunity: GateView
    conversion: GateView
    provenance: list[dict[str, Any]]
    pass_reason: str | None
    probabilities: dict[str, float]
    core_blocked: bool


@dataclass(frozen=True)
class SettlementRow:
    pick_id: str
    event_id: str
    status: str  # pending | settled | unavailable
    recorded_result: float | None
    outcome: str  # win | loss | push | pending | unavailable
    source: str
    captured_at: str
    data_label: str


@dataclass(frozen=True)
class CalibrationBucket:
    key: str
    projections: int
    settlements: int
    wins: int
    losses: int
    pushes: int
    sample_state: str  # ok | insufficient_sample


@dataclass(frozen=True)
class CalibrationView:
    projection_count: int
    settlement_count: int
    by_market: list[CalibrationBucket]
    by_recommendation: list[CalibrationBucket]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class DashboardSnapshot:
    title: str
    data_label: str
    core_status: str
    core_ready: bool
    generated_at: str
    board: list[BoardRow]
    picks: dict[str, PickDetail]
    settlements: list[SettlementRow]
    calibration: CalibrationView
    notices: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
