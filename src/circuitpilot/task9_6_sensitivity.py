"""Deterministic in-bounds, log-aware Task 9.6 local proposals."""

from __future__ import annotations

from hashlib import sha256
import json
from math import exp, log
from typing import Any, Mapping, Sequence

from circuitpilot.experiments.config import SearchParameter


def normalized_position(parameter: SearchParameter, value: float) -> float:
    low, high = float(parameter.low), float(parameter.high)
    return ((log(value) - log(low)) / (log(high) - log(low)) if parameter.log
            else (value - low) / (high - low))


def from_normalized(parameter: SearchParameter, position: float) -> float:
    if not 0.0 <= position <= 1.0:
        raise ValueError("Task 9.6 proposal would leave frozen global bounds")
    low, high = float(parameter.low), float(parameter.high)
    return (exp(log(low) + position * (log(high) - log(low))) if parameter.log
            else low + position * (high - low))


def generate_local_sensitivity_candidates(
    baseline: Mapping[str, float], search_space: Sequence[SearchParameter]
) -> list[dict[str, Any]]:
    expected = {parameter.name for parameter in search_space}
    if set(baseline) != expected or len(expected) != 12:
        raise ValueError("Task 9.6 sensitivity requires exactly 12 frozen variables")
    rows = []
    seen = set()
    for parameter in search_space:
        value = float(baseline[parameter.name])
        if not parameter.contains(value):
            raise ValueError(f"baseline outside frozen global bounds: {parameter.name}")
        position = normalized_position(parameter, value)
        boundary_limited = position <= 0.02 or position >= 0.98
        if position <= 0.02:
            offsets = (0.01, 0.02, 0.03, 0.04)
        elif position >= 0.98:
            offsets = (-0.01, -0.02, -0.03, -0.04)
        else:
            offsets = (-0.02, -0.01, 0.01, 0.02)
        for offset in offsets:
            proposed_value = from_normalized(parameter, position + offset)
            if not parameter.contains(proposed_value):
                raise ValueError(f"rounded sensitivity proposal outside bounds: {parameter.name}")
            candidate = dict(baseline)
            candidate[parameter.name] = proposed_value
            serialized = json.dumps(candidate, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False)
            digest = sha256(serialized.encode()).hexdigest()
            if digest in seen:
                raise ValueError("duplicate sensitivity proposal; do not clip")
            seen.add(digest)
            rows.append({
                "parameter": parameter.name,
                "coordinate": "log" if parameter.log else "linear",
                "baseline_value": value,
                "baseline_normalized_position": position,
                "normalized_offset": offset,
                "candidate_value": proposed_value,
                "relative_value_change": proposed_value / value - 1,
                "boundary_limited": boundary_limited,
                "parameter_vector_sha256": digest,
                "parameters": candidate,
            })
    if len(rows) != 48:
        raise AssertionError("expected 48 local sensitivity proposals")
    return rows
