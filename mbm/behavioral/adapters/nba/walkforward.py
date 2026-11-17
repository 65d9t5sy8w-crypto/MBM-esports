"""Chronological walk-forward validation with purged boundaries.

Hard acceptance criteria:
1. Training data always precedes evaluation data (never shuffle across time).
2. If a training label/feature window overlaps the evaluation period, exclude it.
3. Every prediction uses a recorded point-in-time cutoff.
4. Hyperparameter tuning uses only earlier validation periods (no peeking at
   the current eval fold or later folds).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Sequence

from mbm.behavioral.adapters.nba.leakage import (
    PointInTimeCutoff,
    intervals_overlap,
    observation_window,
    parse_iso,
)
from mbm.behavioral.adapters.nba.types import TimedObservation


@dataclass(frozen=True)
class WalkForwardEvent:
    game_id: str
    game_start: str
    features: tuple[TimedObservation, ...]
    label: TimedObservation | None = None


@dataclass(frozen=True)
class WalkForwardFold:
    fold_index: int
    train_game_ids: tuple[str, ...]
    eval_game_id: str
    eval_start: str
    cutoff: PointInTimeCutoff
    purged_train_keys: tuple[str, ...]
    train_observations: tuple[TimedObservation, ...]
    # Hyperparameter tuning may only use folds with fold_index < this fold.
    tuning_fold_indices: tuple[int, ...]


def purge_overlapping_training(
    train_rows: Sequence[TimedObservation],
    *,
    eval_start: str,
    eval_end: str | None = None,
    purge_gap: timedelta | None = None,
) -> tuple[list[TimedObservation], list[str]]:
    """Drop training rows whose *entire* feature/label window overlaps eval.

    Purging is **not** based on game date alone. An earlier game date whose
    information window (``valid_from``→``valid_to``) or label settlement window
    still touches the evaluation period is excluded. Point observations without
    explicit windows use ``observed_at`` as an instantaneous interval.

    ``eval_end`` defaults to ``eval_start`` (instantaneous event). Optional
    ``purge_gap`` extends the excluded region before eval_start.
    """
    eval_from = parse_iso(eval_start)
    if purge_gap is not None:
        eval_from = eval_from - purge_gap
    eval_to = parse_iso(eval_end) if eval_end else parse_iso(eval_start)
    if eval_to <= eval_from:
        eval_to = eval_from + timedelta(seconds=1)

    kept: list[TimedObservation] = []
    purged: list[str] = []
    for row in train_rows:
        w_from, w_to = observation_window(row)
        if w_to <= w_from:
            w_to = w_from + timedelta(seconds=1)
        # Full-window overlap with the evaluation period → purge, even if the
        # originating game tip-off was earlier than eval_start.
        if intervals_overlap(w_from, w_to, eval_from, eval_to):
            purged.append(row.key)
            continue
        # Observed-at must still strictly precede the evaluation tip-off.
        if parse_iso(row.observed_at) >= parse_iso(eval_start):
            purged.append(row.key)
            continue
        kept.append(row)
    return kept, purged


def chronological_walk_forward(
    events: Sequence[WalkForwardEvent],
    *,
    min_train: int = 1,
    purge_gap: timedelta | None = None,
    recorded_at: str | None = None,
) -> list[WalkForwardFold]:
    """Build purged chronological folds: train on earlier games, eval on later.

    Events are sorted by ``game_start`` ascending. Never shuffled.
    Fold ``i`` trains on events ``[0, i)`` (after purge) and evaluates event ``i``.
    ``tuning_fold_indices`` for fold ``i`` is ``range(0, i)`` — earlier only.
    """
    ordered = sorted(events, key=lambda e: (parse_iso(e.game_start), e.game_id))
    folds: list[WalkForwardFold] = []
    stamp = recorded_at or "1970-01-01T00:00:00Z"

    for i, ev in enumerate(ordered):
        if i < min_train:
            continue
        prior = ordered[:i]
        train_rows: list[TimedObservation] = []
        for p in prior:
            train_rows.extend(p.features)
            if p.label is not None:
                # Labels from prior games are OK for training *targets*, but their
                # windows must still not overlap the eval period (purge).
                train_rows.append(p.label)

        kept, purged = purge_overlapping_training(
            train_rows,
            eval_start=ev.game_start,
            purge_gap=purge_gap,
        )
        # Features for the eval prediction must be pre-cutoff.
        cutoff = PointInTimeCutoff(
            game_id=ev.game_id,
            game_start=ev.game_start,
            as_of=ev.game_start,
            recorded_at=stamp,
        )
        folds.append(
            WalkForwardFold(
                fold_index=len(folds),
                train_game_ids=tuple(p.game_id for p in prior),
                eval_game_id=ev.game_id,
                eval_start=ev.game_start,
                cutoff=cutoff,
                purged_train_keys=tuple(purged),
                train_observations=tuple(kept),
                tuning_fold_indices=tuple(range(0, len(folds))),
            )
        )
    return folds


def select_hyperparameters_earlier_only(
    fold: WalkForwardFold,
    *,
    candidate_scores_by_fold: dict[int, dict[str, float]],
    score_key: str = "brier",
    lower_is_better: bool = True,
) -> str:
    """Pick hyperparameters using only earlier validation folds.

    ``candidate_scores_by_fold[fold_index][param_name] = metric``.
    Raises if any score from the current or later fold is supplied for selection.
    """
    allowed = set(fold.tuning_fold_indices)
    illegal = [idx for idx in candidate_scores_by_fold if idx not in allowed]
    if illegal:
        raise ValueError(
            f"hyperparameter tuning must use only earlier validation periods; "
            f"illegal fold indices {sorted(illegal)} for fold {fold.fold_index}"
        )
    if not allowed:
        raise ValueError("no earlier folds available for hyperparameter tuning")

    totals: dict[str, list[float]] = {}
    for idx in allowed:
        scores = candidate_scores_by_fold.get(idx) or {}
        for name, val in scores.items():
            totals.setdefault(name, []).append(float(val))
    if not totals:
        raise ValueError("no candidate scores on earlier folds")

    def agg(vals: list[float]) -> float:
        return sum(vals) / len(vals)

    ranked = sorted(
        ((name, agg(vals)) for name, vals in totals.items()),
        key=lambda kv: kv[1],
        reverse=not lower_is_better,
    )
    return ranked[0][0]


def run_walk_forward(
    events: Sequence[WalkForwardEvent],
    predict_fn: Callable[[WalkForwardFold, WalkForwardEvent], Any],
    *,
    min_train: int = 1,
    purge_gap: timedelta | None = None,
) -> list[tuple[WalkForwardFold, Any]]:
    """Execute predict_fn on each fold's eval event with that fold's cutoff."""
    by_id = {e.game_id: e for e in events}
    folds = chronological_walk_forward(events, min_train=min_train, purge_gap=purge_gap)
    out: list[tuple[WalkForwardFold, Any]] = []
    for fold in folds:
        ev = by_id[fold.eval_game_id]
        out.append((fold, predict_fn(fold, ev)))
    return out


def assert_training_precedes_evaluation(fold: WalkForwardFold, events: Sequence[WalkForwardEvent]) -> None:
    by_id = {e.game_id: e for e in events}
    eval_start = parse_iso(fold.eval_start)
    for gid in fold.train_game_ids:
        start = parse_iso(by_id[gid].game_start)
        if start >= eval_start:
            raise AssertionError(
                f"training game {gid} start {start.isoformat()} does not precede "
                f"eval {fold.eval_game_id} at {eval_start.isoformat()}"
            )
