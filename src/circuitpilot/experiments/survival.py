"""Dependency-free Kaplan-Meier estimates for time to first feasible design."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable


@dataclass(frozen=True, slots=True)
class SurvivalPoint:
    time: int
    survival_probability: float
    at_risk: int
    events: int
    censored: int


@dataclass(frozen=True, slots=True)
class KaplanMeierEstimate:
    points: tuple[SurvivalPoint, ...]
    horizon: int
    rmst: float
    median_time_to_event: int | None


def kaplan_meier(
    observations: Iterable[tuple[int, bool]], *, horizon: int | None = None
) -> KaplanMeierEstimate:
    """Estimate survival and restricted mean time without feasibility.

    Each observation is ``(evaluation_time, event_observed)``.  Censored runs
    remain at risk through their censoring time and never become events.
    """
    values = list(observations)
    if not values:
        raise ValueError("Kaplan-Meier requires at least one observation")
    for time, event in values:
        if isinstance(time, bool) or not isinstance(time, int) or time <= 0:
            raise ValueError("survival times must be positive integers")
        if not isinstance(event, bool):
            raise ValueError("event_observed must be boolean")
    maximum = max(time for time, _ in values)
    resolved_horizon = maximum if horizon is None else horizon
    if (
        isinstance(resolved_horizon, bool)
        or not isinstance(resolved_horizon, int)
        or resolved_horizon <= 0
        or resolved_horizon < maximum
    ):
        raise ValueError("survival horizon must be an integer at least max(time)")

    survival = 1.0
    at_risk = len(values)
    points: list[SurvivalPoint] = []
    rmst = 0.0
    last_time = 0
    median_time: int | None = None
    for time in sorted({item[0] for item in values}):
        rmst += survival * (time - last_time)
        events = sum(t == time and event for t, event in values)
        censored = sum(t == time and not event for t, event in values)
        if events:
            survival *= 1.0 - events / at_risk
        if not isfinite(survival) or not 0.0 <= survival <= 1.0:
            raise ValueError("invalid Kaplan-Meier survival probability")
        points.append(SurvivalPoint(time, survival, at_risk, events, censored))
        if median_time is None and survival <= 0.5:
            median_time = time
        at_risk -= events + censored
        last_time = time
    if last_time < resolved_horizon:
        rmst += survival * (resolved_horizon - last_time)
    return KaplanMeierEstimate(
        points=tuple(points),
        horizon=resolved_horizon,
        rmst=rmst,
        median_time_to_event=median_time,
    )
