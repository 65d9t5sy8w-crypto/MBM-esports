"""Point-in-time / no-lookahead enforcement for NBA features and markets.

Hard rules:
1. Features, lines, injuries, and market snapshots must be knowable strictly
   before each game's start (``as_of`` / tip-off cutoff).
2. Settlement-driven labels are never allowed as model inputs.
3. Injected future information must raise / return an explicit rejection.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence

from mbm.behavioral.adapters.nba.types import TimedObservation


def parse_iso(ts: str) -> datetime:
    text = str(ts).strip().replace("Z", "+00:00")
    # Date-only → midnight UTC. Do not rewrite space-separated datetimes.
    if "T" not in text and " " not in text:
        text = f"{text}T00:00:00+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def try_parse_iso(ts: str) -> datetime | None:
    """Return parsed UTC datetime, or None when the timestamp is unusable."""
    try:
        return parse_iso(ts)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class PointInTimeCutoff:
    """Recorded cutoff for a single prediction.

    Every prediction must carry one of these. ``as_of`` is the latest moment
    information may be used; conventionally the scheduled tip-off (exclusive).
    """

    game_id: str
    game_start: str
    as_of: str
    recorded_at: str

    def __post_init__(self) -> None:
        start = parse_iso(self.game_start)
        as_of = parse_iso(self.as_of)
        if as_of > start:
            raise ValueError(
                f"PointInTimeCutoff as_of {self.as_of} must not exceed game_start "
                f"{self.game_start} (lookahead)"
            )


def filter_as_of(
    rows: Sequence[TimedObservation],
    *,
    as_of: str,
    allow_labels: bool = False,
) -> list[TimedObservation]:
    """Keep observations knowable strictly before ``as_of``.

    Rows with ``observed_at >= as_of`` are dropped. Labels are dropped unless
    ``allow_labels=True`` (evaluation-only paths).
    """
    cutoff = parse_iso(as_of)
    kept: list[TimedObservation] = []
    for row in rows:
        if row.is_label and not allow_labels:
            continue
        if parse_iso(row.observed_at) >= cutoff:
            continue
        kept.append(row)
    return kept


def assert_no_lookahead(
    rows: Sequence[TimedObservation],
    *,
    as_of: str,
    context: str = "features",
) -> None:
    """Raise if any non-label input is dated on/after the cutoff."""
    cutoff = parse_iso(as_of)
    leaks = [
        row
        for row in rows
        if (not row.is_label) and parse_iso(row.observed_at) >= cutoff
    ]
    if leaks:
        keys = ", ".join(sorted({r.key for r in leaks})[:8])
        raise ValueError(
            f"lookahead rejected in {context}: {len(leaks)} observation(s) "
            f"with observed_at >= as_of={as_of} (e.g. {keys})"
        )


def reject_future_information(
    rows: Sequence[TimedObservation],
    *,
    cutoff: PointInTimeCutoff,
) -> tuple[list[TimedObservation], tuple[str, ...]]:
    """Filter + report rejected future rows (for tests that inject leakage)."""
    assert_no_lookahead(
        [r for r in rows if not r.is_label],
        as_of=cutoff.as_of,
        context=f"game:{cutoff.game_id}",
    )
    # Labels after tip-off are fine for settlement grading only — strip from inputs.
    clean = filter_as_of(rows, as_of=cutoff.as_of, allow_labels=False)
    rejected = [
        f"{r.key}@{r.observed_at}"
        for r in rows
        if (not r.is_label) and parse_iso(r.observed_at) >= parse_iso(cutoff.as_of)
    ]
    # assert_no_lookahead already raises; rejected list is empty on success path
    # when called after filtering. Keep for callers that pre-filter.
    _ = rejected
    return clean, tuple(rejected)


def intervals_overlap(a_from: datetime, a_to: datetime, b_from: datetime, b_to: datetime) -> bool:
    """Half-open interval overlap: [from, to)."""
    return a_from < b_to and b_from < a_to


def observation_window(row: TimedObservation) -> tuple[datetime, datetime]:
    """Resolve a training observation's feature/label window."""
    if row.valid_from and row.valid_to:
        return parse_iso(row.valid_from), parse_iso(row.valid_to)
    # Point observation: treat as instantaneous at observed_at.
    t = parse_iso(row.observed_at)
    return t, t


def market_snapshot_usable(*, captured_at: str, game_start: str) -> bool:
    """Usable only when ``captured_at`` parses and is strictly before the cutoff.

    Callers should pass ``cutoff.as_of`` (prediction time), not merely tip-off,
    so lines that arrive between as_of and tip cannot leak into the decision.
    Unparseable timestamps are rejected rather than raising.
    """
    captured = try_parse_iso(captured_at)
    cutoff = try_parse_iso(game_start)
    if captured is None or cutoff is None:
        return False
    return captured < cutoff


def injury_usable(*, reported_at: str, game_start: str) -> bool:
    return parse_iso(reported_at) < parse_iso(game_start)


def ensure_cutoff_recorded(
    cutoff: PointInTimeCutoff | None,
    *,
    game_id: str,
    game_start: str | None = None,
) -> PointInTimeCutoff:
    if cutoff is None:
        raise ValueError(
            f"every prediction requires a recorded PointInTimeCutoff (game_id={game_id})"
        )
    if cutoff.game_id != str(game_id):
        raise ValueError(
            f"cutoff game_id {cutoff.game_id!r} does not match prediction game {game_id!r}"
        )
    if game_start is not None:
        expected = parse_iso(game_start)
        got_start = parse_iso(cutoff.game_start)
        if got_start != expected:
            raise ValueError(
                f"cutoff game_start {cutoff.game_start!r} does not match "
                f"fixture start {game_start!r}"
            )
        # as_of must not exceed this fixture's tip-off (already enforced in
        # PointInTimeCutoff.__post_init__ against cutoff.game_start).
        if parse_iso(cutoff.as_of) > expected:
            raise ValueError(
                f"cutoff as_of {cutoff.as_of!r} exceeds fixture start {game_start!r}"
            )
    return cutoff
