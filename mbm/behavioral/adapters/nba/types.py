"""NBA-native types for research windows, props, and market comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class NbaRecommendation(str, Enum):
    MORE = "MORE"
    LESS = "LESS"
    PASS = "PASS"


ALLOWED_NBA_ACTIONS = frozenset(r.value for r in NbaRecommendation)


class AnalysisWindow(str, Enum):
    LAST_5 = "last_5"
    LAST_10 = "last_10"
    SEASON = "season"
    OPPONENT = "opponent"


@dataclass(frozen=True)
class TimedObservation:
    """Any feature/label/market row with an observed timestamp and validity interval.

    ``observed_at`` is when the fact became knowable.
    ``valid_from`` / ``valid_to`` bound the feature/label window used in training.
    Settlement labels must never be used as inputs; they may only appear as
    ``is_label=True`` and are excluded from feature assembly.
    """

    key: str
    observed_at: str  # ISO-8601
    value: Any
    valid_from: str | None = None
    valid_to: str | None = None
    is_label: bool = False
    source: str = "unknown"


@dataclass(frozen=True)
class WindowSummary:
    window: AnalysisWindow
    sample_size: int
    mean: float | None
    values: tuple[float, ...]
    as_of: str
    opponent_team_id: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketSnapshot:
    vendor: str
    prop_type: str
    line: float
    more_odds: int | None
    less_odds: int | None
    captured_at: str
    source_identity: str
    raw_evidence_ref: str
    game_id: str
    player_id: str | None = None


@dataclass(frozen=True)
class PropProbability:
    more: float
    less: float
    line: float
    projection: float
    sample_size: int
    failure_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class MarketComparison:
    """Independent MBM projection vs sportsbook — never auto-defers to market."""

    mbm_projection: float
    market_line: float
    mbm_more_prob: float
    market_implied_more: float | None
    edge_more: float | None
    deferred_to_market: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MetricsReport:
    hit_rate: float | None
    brier_score: float | None
    calibration_error: float | None
    realized_roi: float | None
    sample_size: int
    hit_rate_n: int
    brier_n: int
    calibration_n: int
    roi_n: int
    notes: tuple[str, ...] = ()
