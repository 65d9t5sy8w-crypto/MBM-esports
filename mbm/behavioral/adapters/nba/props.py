"""Prop-specific MORE/LESS probabilities and failure paths."""

from __future__ import annotations

import math
from typing import Sequence

from mbm.behavioral.adapters.nba.types import PropProbability, WindowSummary


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def american_to_implied_prob(odds: int | None) -> float | None:
    if odds is None:
        return None
    if odds == 0:
        return None
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return abs(odds) / (abs(odds) + 100.0)


def empirical_more_less(
    values: Sequence[float],
    line: float,
) -> tuple[float, float, int]:
    """Empirical P(MORE)/P(LESS) from historical outcomes vs line (pushes excluded)."""
    decisive = [v for v in values if v != line]
    n = len(decisive)
    if n == 0:
        return 0.5, 0.5, 0
    more = sum(1 for v in decisive if v > line) / n
    return more, 1.0 - more, n


def gaussian_more_prob(projection: float, line: float, *, std: float) -> float:
    """Simple continuous approximation; std must be > 0."""
    if std <= 0:
        return 1.0 if projection > line else (0.0 if projection < line else 0.5)
    # P(X > line) with X ~ N(projection, std^2)
    z = (line - projection) / (std * math.sqrt(2.0))
    # erfc-based survival
    return _clamp01(0.5 * math.erfc(z))


def prop_probabilities(
    windows: dict[str, WindowSummary],
    *,
    line: float,
    min_sample: int = 5,
) -> PropProbability:
    failures: list[str] = []
    # Prefer last_10, else last_5, else season.
    preferred = None
    for key in ("last_10", "last_5", "season", "opponent"):
        w = windows.get(key)
        if w and w.sample_size >= min_sample and w.mean is not None:
            preferred = w
            break
        if w and w.sample_size < min_sample:
            failures.append(
                f"{key}_insufficient_sample:n={w.sample_size}:min={min_sample}"
            )

    if preferred is None:
        failures.append("no_usable_research_window")
        return PropProbability(
            more=0.5,
            less=0.5,
            line=line,
            projection=line,
            sample_size=0,
            failure_paths=tuple(failures),
        )

    values = preferred.values
    more_emp, less_emp, n_emp = empirical_more_less(values, line)
    # Blend empirical with Gaussian around mean using sample std.
    if len(values) >= 2:
        mean = preferred.mean if preferred.mean is not None else line
        var = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
        std = math.sqrt(var) if var > 0 else 1.0
        more_g = gaussian_more_prob(mean, line, std=std)
        more = 0.5 * more_emp + 0.5 * more_g
    else:
        mean = preferred.mean if preferred.mean is not None else line
        more = more_emp
        failures.append("single_sample_gaussian_skipped")

    more = _clamp01(more)
    less = _clamp01(1.0 - more)
    return PropProbability(
        more=more,
        less=less,
        line=line,
        projection=float(mean),
        sample_size=preferred.sample_size,
        failure_paths=tuple(failures),
    )
