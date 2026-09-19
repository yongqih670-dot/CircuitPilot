"""Deterministic paired and survival statistics for Task 8."""

from __future__ import annotations

from dataclasses import dataclass
import random
from statistics import fmean, median
from typing import Iterable


BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 82_008


def _percentile(values: list[float], percentage: float) -> float:
    """Return a linearly interpolated percentile without optional dependencies."""
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * percentage / 100.0
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def paired_effect(
    differences: Iterable[float],
    *,
    seed: int = BOOTSTRAP_SEED,
    resamples: int = BOOTSTRAP_RESAMPLES,
) -> dict[str, float | int | list[float]]:
    """Summarize paired differences with the pre-registered bootstrap CI."""
    values = [float(value) for value in differences]
    if not values:
        raise ValueError("paired effect requires at least one difference")
    if resamples <= 0:
        raise ValueError("bootstrap resamples must be positive")
    rng = random.Random(seed)
    count = len(values)
    bootstrap_means = [
        fmean(values[rng.randrange(count)] for _ in range(count))
        for _ in range(resamples)
    ]
    return {
        "pairs": count,
        "mean_difference": fmean(values),
        "median_difference": median(values),
        "ci95_low": _percentile(bootstrap_means, 2.5),
        "ci95_high": _percentile(bootstrap_means, 97.5),
        "paired_differences": values,
        "bootstrap_seed": seed,
        "bootstrap_resamples": resamples,
    }


@dataclass(frozen=True, slots=True)
class KaplanMeierPoint:
    time: float
    survival_probability: float
    at_risk: int
    events: int
    censored: int


@dataclass(frozen=True, slots=True)
class KaplanMeierEstimate:
    points: tuple[KaplanMeierPoint, ...]
    horizon: float
    rmst: float
    median_time_to_event: float | None


def kaplan_meier(
    observations: Iterable[tuple[float, bool]], *, horizon: float
) -> KaplanMeierEstimate:
    """Kaplan-Meier and RMST with deterministic truncation at a shared horizon.

    Follow-up beyond ``horizon`` is administratively censored at the horizon.
    Zero-cost censoring is permitted because a hierarchical run can execute no
    AC or transient analyses before exhausting its candidate budget.
    """
    raw = [(float(time), event) for time, event in observations]
    if not raw:
        raise ValueError("Kaplan-Meier requires at least one observation")
    if horizon < 0.0:
        raise ValueError("Kaplan-Meier horizon cannot be negative")
    if any(time < 0.0 or not isinstance(event, bool) for time, event in raw):
        raise ValueError("invalid Kaplan-Meier observation")
    values = [
        (min(time, horizon), event and time <= horizon)
        for time, event in raw
    ]
    survival = 1.0
    at_risk = len(values)
    last_time = 0.0
    rmst = 0.0
    median_time: float | None = None
    points: list[KaplanMeierPoint] = []
    for time in sorted({item[0] for item in values}):
        rmst += survival * (time - last_time)
        events = sum(value == time and event for value, event in values)
        censored = sum(value == time and not event for value, event in values)
        if events:
            survival *= 1.0 - events / at_risk
        points.append(
            KaplanMeierPoint(time, survival, at_risk, events, censored)
        )
        if median_time is None and survival <= 0.5:
            median_time = time
        at_risk -= events + censored
        last_time = time
    if last_time < horizon:
        rmst += survival * (horizon - last_time)
    return KaplanMeierEstimate(tuple(points), horizon, rmst, median_time)
