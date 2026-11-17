"""Walk-forward result metrics reported separately with sample sizes.

Reports hit rate, Brier score, calibration error, and realized ROI — each with
its own ``n``. Never fabricates performance on empty samples.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from mbm.behavioral.adapters.nba.types import MetricsReport

MIN_CALIBRATION_SAMPLE = 20


@dataclass(frozen=True)
class ScoredPrediction:
    """One evaluated prediction after the game settles."""

    game_id: str
    # Probability assigned to the MORE side (or chosen side via ``took_more``).
    p_more: float
    took_more: bool
    # Actual MORE occurred?
    actual_more: bool | None
    # Decimal stake ROI contribution if a unit bet were placed; None if PASS / no bet.
    unit_roi: float | None
    # Predicted probability for the chosen side (for Brier on decisions).
    p_chosen: float


def hit_rate(rows: Sequence[ScoredPrediction]) -> tuple[float | None, int]:
    graded = [r for r in rows if r.actual_more is not None and r.unit_roi is not None]
    n = len(graded)
    if n == 0:
        return None, 0
    hits = sum(
        1
        for r in graded
        if (r.took_more and r.actual_more) or ((not r.took_more) and (not r.actual_more))
    )
    return hits / n, n


def brier_score(rows: Sequence[ScoredPrediction]) -> tuple[float | None, int]:
    graded = [r for r in rows if r.actual_more is not None]
    n = len(graded)
    if n == 0:
        return None, 0
    total = 0.0
    for r in graded:
        y = 1.0 if r.actual_more else 0.0
        total += (r.p_more - y) ** 2
    return total / n, n


def calibration_error(
    rows: Sequence[ScoredPrediction],
    *,
    bins: int = 10,
    min_sample: int = MIN_CALIBRATION_SAMPLE,
) -> tuple[float | None, int]:
    """Mean absolute calibration error across probability bins."""
    graded = [r for r in rows if r.actual_more is not None]
    n = len(graded)
    if n < min_sample:
        return None, n
    bucket_sums = [0.0] * bins
    bucket_counts = [0] * bins
    bucket_outcomes = [0.0] * bins
    for r in graded:
        idx = min(bins - 1, max(0, int(r.p_more * bins)))
        bucket_sums[idx] += r.p_more
        bucket_counts[idx] += 1
        bucket_outcomes[idx] += 1.0 if r.actual_more else 0.0
    errs: list[float] = []
    for i in range(bins):
        if bucket_counts[i] == 0:
            continue
        avg_p = bucket_sums[i] / bucket_counts[i]
        freq = bucket_outcomes[i] / bucket_counts[i]
        errs.append(abs(avg_p - freq))
    if not errs:
        return None, n
    return sum(errs) / len(errs), n


def realized_roi(rows: Sequence[ScoredPrediction]) -> tuple[float | None, int]:
    bets = [r for r in rows if r.unit_roi is not None]
    n = len(bets)
    if n == 0:
        return None, 0
    return sum(r.unit_roi for r in bets if r.unit_roi is not None) / n, n


def build_metrics_report(rows: Sequence[ScoredPrediction]) -> MetricsReport:
    hr, hr_n = hit_rate(rows)
    br, br_n = brier_score(rows)
    cal, cal_n = calibration_error(rows)
    roi, roi_n = realized_roi(rows)
    notes = [
        "metrics reported separately with sample sizes",
        f"calibration requires n>={MIN_CALIBRATION_SAMPLE} (else null)",
        "PASS / non-bet rows excluded from hit_rate and realized_roi denominators",
    ]
    if cal is None and cal_n < MIN_CALIBRATION_SAMPLE:
        notes.append("calibration_insufficient_sample")
    return MetricsReport(
        hit_rate=hr,
        brier_score=br,
        calibration_error=cal,
        realized_roi=roi,
        sample_size=len(rows),
        hit_rate_n=hr_n,
        brier_n=br_n,
        calibration_n=cal_n,
        roi_n=roi_n,
        notes=tuple(notes),
    )
