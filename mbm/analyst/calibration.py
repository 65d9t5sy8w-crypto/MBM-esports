"""Calibration summaries — never fabricate performance with tiny samples."""

from __future__ import annotations

from collections import defaultdict

from mbm.analyst.models import BoardRow, CalibrationBucket, CalibrationView, SettlementRow

MIN_SAMPLE = 20


def _bucket(key: str, projections: int, settlements: list[SettlementRow]) -> CalibrationBucket:
    settled = [s for s in settlements if s.status == "settled"]
    wins = sum(1 for s in settled if s.outcome == "win")
    losses = sum(1 for s in settled if s.outcome == "loss")
    pushes = sum(1 for s in settled if s.outcome == "push")
    n = len(settled)
    state = "ok" if n >= MIN_SAMPLE else "insufficient_sample"
    return CalibrationBucket(
        key=key,
        projections=projections,
        settlements=n,
        wins=wins,
        losses=losses,
        pushes=pushes,
        sample_state=state,
    )


def build_calibration(board: list[BoardRow], settlements: list[SettlementRow]) -> CalibrationView:
    by_market: dict[str, list[BoardRow]] = defaultdict(list)
    by_rec: dict[str, list[BoardRow]] = defaultdict(list)
    for row in board:
        by_market[row.stat].append(row)
        by_rec[row.recommendation].append(row)

    settle_by_pick = {s.pick_id: s for s in settlements}

    market_buckets = []
    for key, rows in sorted(by_market.items()):
        related = [settle_by_pick[r.pick_id] for r in rows if r.pick_id in settle_by_pick]
        market_buckets.append(_bucket(key, len(rows), related))

    rec_buckets = []
    for key, rows in sorted(by_rec.items()):
        related = [settle_by_pick[r.pick_id] for r in rows if r.pick_id in settle_by_pick]
        rec_buckets.append(_bucket(key, len(rows), related))

    notes = (
        f"Minimum settled sample for rates: {MIN_SAMPLE}.",
        "insufficient_sample means win-rate style metrics must not be treated as performance.",
        "Fixture/demo settlements do not imply live edge.",
    )
    return CalibrationView(
        projection_count=len(board),
        settlement_count=sum(1 for s in settlements if s.status == "settled"),
        by_market=market_buckets,
        by_recommendation=rec_buckets,
        notes=notes,
    )
