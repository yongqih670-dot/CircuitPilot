"""Supported-horizon survival estimates for the Task 9.5 correction audit.

Historical estimators and result files remain unchanged.  This module adds the
strict support rule used by the independent correction package.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class SupportedEstimate:
    horizon: float
    rmst: float
    median: float | None
    events: int
    censored: int
    points: tuple[tuple[float, float, int, int, int], ...]


def common_supported_horizon(
    groups: Mapping[str, Iterable[tuple[float, bool]]],
) -> float:
    """Largest time supported by every comparison group.

    The maximum observed follow-up is the last defensible time for a group.
    Crossing it would extend a positive KM tail after its risk set has vanished.
    """
    if not groups:
        raise ValueError("at least one comparison group is required")
    maxima = []
    for observations in groups.values():
        values = list(observations)
        if not values:
            raise ValueError("empty comparison group")
        if any(
            not isfinite(float(time)) or float(time) < 0 or not isinstance(event, bool)
            for time, event in values
        ):
            raise ValueError("invalid survival observation")
        maxima.append(max(float(time) for time, _ in values))
    return min(maxima)


def supported_km(
    observations: Iterable[tuple[float, bool]], *, horizon: float,
) -> SupportedEstimate:
    """Administratively censor at `horizon` and refuse unsupported tails."""
    raw = [(float(time), event) for time, event in observations]
    if not raw:
        raise ValueError("at least one observation is required")
    if any(not isfinite(time) or time < 0 or not isinstance(event, bool) for time, event in raw):
        raise ValueError("invalid survival observation")
    if not isfinite(horizon) or horizon < 0 or horizon > max(time for time, _ in raw):
        raise ValueError("RMST horizon exceeds observed support")
    values = [(min(time, horizon), bool(event and time <= horizon)) for time, event in raw]
    survival = 1.0
    at_risk = len(values)
    previous = 0.0
    rmst = 0.0
    median = None
    points = []
    for time in sorted({time for time, _ in values}):
        rmst += survival * (time - previous)
        events = sum(item_time == time and event for item_time, event in values)
        censored = sum(item_time == time and not event for item_time, event in values)
        if events:
            survival *= 1.0 - events / at_risk
        points.append((time, survival, at_risk, events, censored))
        if median is None and survival <= 0.5:
            median = time
        at_risk -= events + censored
        previous = time
    if previous < horizon:
        if at_risk == 0 and survival > 0:
            raise ValueError("RMST would integrate beyond the last risk set")
        rmst += survival * (horizon - previous)
    return SupportedEstimate(
        horizon, rmst, median, sum(event for _, event in raw),
        sum(not event for _, event in raw), tuple(points),
    )
