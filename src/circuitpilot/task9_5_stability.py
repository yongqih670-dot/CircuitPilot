"""Task 9.5 audit-only inventory of every measured zero-dB gain crossing."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log10

from circuitpilot.parser import ACAnalysisResult
from circuitpilot.sky130_two_stage_ota import _unwrap_phase_deg


CRITICAL_PM_SEMANTICS = "minimum_phase_margin_over_descending_unity_crossings_v2"


@dataclass(frozen=True, slots=True)
class Crossing:
    frequency_hz: float
    phase_margin_deg: float
    direction: str


def all_unity_crossings(response: ACAnalysisResult) -> tuple[Crossing, ...]:
    """Log-interpolate every up/down unity crossing and unwrapped phase."""
    frequency, gain, phase = response.frequency_hz, response.gain_db, response.phase_deg
    if not (len(frequency) == len(gain) == len(phase)) or len(frequency) < 2:
        raise ValueError("invalid AC response lengths")
    if any(not all(isfinite(float(x)) for x in values) for values in zip(frequency, gain, phase)):
        raise ValueError("non-finite AC response")
    if any(float(frequency[index]) <= float(frequency[index - 1])
           for index in range(1, len(frequency))):
        raise ValueError("AC frequencies must strictly increase")
    unwrapped = _unwrap_phase_deg(phase)
    crossings = []
    for index in range(1, len(gain)):
        upper, lower = float(gain[index - 1]), float(gain[index])
        if upper >= 0 and lower < 0:
            direction = "descending"
        elif upper <= 0 and lower > 0:
            direction = "ascending"
        else:
            continue
        fraction = -upper / (lower - upper)
        log_frequency = log10(float(frequency[index - 1])) + fraction * (
            log10(float(frequency[index])) - log10(float(frequency[index - 1]))
        )
        phase_at_crossing = unwrapped[index - 1] + fraction * (
            unwrapped[index] - unwrapped[index - 1]
        )
        crossings.append(Crossing(10 ** log_frequency,
                                  180.0 + phase_at_crossing, direction))
    return tuple(crossings)


def first_and_critical_pm(
    crossings: tuple[Crossing, ...],
) -> tuple[float | None, float | None]:
    descending = [item.phase_margin_deg for item in crossings
                  if item.direction == "descending"]
    return (descending[0], min(descending)) if descending else (None, None)
