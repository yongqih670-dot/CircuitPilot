"""Frozen search, specification, objective, and fairness helpers for Task 7."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite, log10
from typing import Any, Mapping, Sequence

from circuitpilot.sky130_two_stage_ota import (
    PhaseMarginStatus,
    SlewStatus,
    UgfStatus,
)


METHODS = ("random", "de", "tpe", "bo")
SEARCH_SPACE_VERSION = "task7_role_matched_12d_prior_v1"
DIFFICULTY_PROTOCOL_VERSION = "task7_sobol512_difficulty_ladder_v1"
OBJECTIVE_SEMANTICS_VERSION = "task7_lexicographic_feasibility_then_power_v1"
STATISTICAL_PLAN_VERSION = "task7_candidate_km_rmst_pairwise_v1"
TASK7_BENCHMARK_HASH = (
    "144100e168ca5f550c6ca0bd5a29788f669d0e34cd9008c5a7fe2099e8cb8c1c"
)
TASK7_SEARCH_SPACE_HASH = (
    "36e72bd54d2b1850af1ce1c8a69dbe7de22f552d49713edfbb0d3de83cd4f6db"
)
TASK7_CALIBRATION_CSV_HASH = (
    "27d0603b460005c9fe9e89a584a2850548bd7c8fb31a9917aa09994bf45883ef"
)
TASK7_FROZEN_YAML_BYTE_HASH = (
    "077a42c053dfa59b6deb6e19dbca6cd74bec8122ebcb17998b906a4aa590df28"
)
TASK7_FROZEN_SPECIFICATION_HASH = (
    "30c8efb875f19bc46f956dfefb2016411e1aec5c6f877bc5996a0a1af0e24775"
)
TASK7_MEASUREMENT_DOCUMENT_HASH = (
    "13756787621f27401ba05a951f839dc14fd6a249d38266f47482e6409e38d553"
)
TASK7_COST_DOCUMENT_HASH = (
    "c3b2de5136c9acc9637473be8acd19ee7f9cdeab287ac08a45774e5177391aff"
)
TASK7_STATISTICAL_DOCUMENT_HASH = (
    "c30648608f0cd72da1c1e3c91f908d254ac5929815d8a03eb7ad1dff345c4a66"
)
TASK5_BENCHMARK_HASH = (
    "57d2183621ecf37e5ca22e012452c43fce6459be7d347a5cfc93d0b394c14378"
)
TASK6_POLICY_FAMILY_HASH = (
    "53b1eb73160b4d069135f406613cd1249fcdd002bfd6cb2b0c8892da1c3b4867"
)

# name, low, high, logarithmic
SEARCH_DIMENSIONS = (
    ("input_pair_width_m", 0.84e-6, 30.0e-6, True),
    ("input_pair_length_m", 0.15e-6, 1.0e-6, False),
    ("first_stage_load_width_m", 0.84e-6, 40.0e-6, True),
    ("first_stage_load_length_m", 0.15e-6, 1.2e-6, False),
    ("tail_width_m", 0.42e-6, 30.0e-6, True),
    ("tail_length_m", 0.15e-6, 1.2e-6, False),
    ("second_stage_width_m", 0.84e-6, 60.0e-6, True),
    ("second_stage_length_m", 0.15e-6, 1.2e-6, False),
    ("second_load_width_m", 0.84e-6, 60.0e-6, True),
    ("second_load_length_m", 0.15e-6, 1.2e-6, False),
    ("second_load_bias_v", 0.25, 1.20, False),
    ("compensation_capacitance_f", 0.05e-12, 5.0e-12, True),
)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def protocol_family_hash() -> str:
    """Bind all fairness-relevant Task 7 semantic identities."""
    return stable_hash(
        {
            "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
            "task7_search_space_hash": TASK7_SEARCH_SPACE_HASH,
            "task7_frozen_yaml_byte_hash": TASK7_FROZEN_YAML_BYTE_HASH,
            "task7_frozen_specification_hash": TASK7_FROZEN_SPECIFICATION_HASH,
            "task7_measurement_document_hash": TASK7_MEASUREMENT_DOCUMENT_HASH,
            "task7_cost_document_hash": TASK7_COST_DOCUMENT_HASH,
            "task7_statistical_document_hash": TASK7_STATISTICAL_DOCUMENT_HASH,
            "task7_calibration_csv_hash": TASK7_CALIBRATION_CSV_HASH,
            "search_space_version": SEARCH_SPACE_VERSION,
            "difficulty_protocol_version": DIFFICULTY_PROTOCOL_VERSION,
            "objective_semantics_version": OBJECTIVE_SEMANTICS_VERSION,
            "statistical_plan_version": STATISTICAL_PLAN_VERSION,
            "formal_candidate_budget": 50,
            "methods": METHODS,
            "seeds": list(range(10)),
            "task5_benchmark_hash": TASK5_BENCHMARK_HASH,
            "task6_policy_family_hash": TASK6_POLICY_FAMILY_HASH,
        }
    )


def decode_unit_candidate(coordinates: Sequence[float]) -> dict[str, float]:
    if len(coordinates) != len(SEARCH_DIMENSIONS):
        raise ValueError("Task 7 unit candidate must have twelve dimensions")
    candidate: dict[str, float] = {}
    for coordinate, (name, low, high, logarithmic) in zip(
        coordinates, SEARCH_DIMENSIONS
    ):
        unit = float(coordinate)
        if not isfinite(unit) or not 0.0 <= unit <= 1.0:
            raise ValueError("Task 7 unit coordinates must be finite in [0, 1]")
        if logarithmic:
            value = 10.0 ** (log10(low) + unit * (log10(high) - log10(low)))
        else:
            value = low + unit * (high - low)
        candidate[name] = max(low, min(high, value))
    return candidate


@dataclass(frozen=True, slots=True)
class Task7Specification:
    gain_min_db: float
    ugf_min_hz: float
    phase_margin_min_deg: float
    power_max_w: float
    positive_slew_min_v_per_s: float
    negative_slew_min_v_per_s: float
    output_min_v: float
    output_max_v: float
    require_operating_region: bool = True

    def __post_init__(self) -> None:
        for name in (
            "gain_min_db",
            "ugf_min_hz",
            "phase_margin_min_deg",
            "power_max_w",
            "positive_slew_min_v_per_s",
            "negative_slew_min_v_per_s",
            "output_min_v",
            "output_max_v",
        ):
            value = float(getattr(self, name))
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")
        if (
            self.ugf_min_hz <= 0
            or self.power_max_w <= 0
            or self.positive_slew_min_v_per_s <= 0
            or self.negative_slew_min_v_per_s <= 0
        ):
            raise ValueError("Task 7 frequency, power, and slew limits must be positive")
        if not self.output_min_v < self.output_max_v:
            raise ValueError("Task 7 output limits must be increasing")
        if not self.require_operating_region:
            raise ValueError("Task 7 always requires all-device operating-region validity")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Task7Specification":
        allowed = {
            "gain_min_db",
            "ugf_min_hz",
            "phase_margin_min_deg",
            "power_max_w",
            "positive_slew_min_v_per_s",
            "negative_slew_min_v_per_s",
            "output_min_v",
            "output_max_v",
        }
        if set(value) != allowed:
            raise ValueError("Task 7 specification fields do not match the frozen schema")
        return cls(**{name: float(value[name]) for name in allowed})

    def to_dict(self) -> dict[str, float | bool]:
        return {
            "gain_min_db": self.gain_min_db,
            "ugf_min_hz": self.ugf_min_hz,
            "phase_margin_min_deg": self.phase_margin_min_deg,
            "power_max_w": self.power_max_w,
            "positive_slew_min_v_per_s": self.positive_slew_min_v_per_s,
            "negative_slew_min_v_per_s": self.negative_slew_min_v_per_s,
            "output_min_v": self.output_min_v,
            "output_max_v": self.output_max_v,
            "require_operating_region": self.require_operating_region,
        }


@dataclass(frozen=True, slots=True)
class Task7ObjectiveEvaluation:
    objective_value: float
    constraint_violation: float
    constraint_components: Mapping[str, float]
    is_feasible: bool


def evaluate_task7_objective(
    metrics: Mapping[str, float | None],
    specification: Task7Specification,
    *,
    ugf_status: str,
    phase_margin_status: str,
    positive_slew_status: str,
    negative_slew_status: str,
) -> Task7ObjectiveEvaluation:
    """Apply all hard constraints, then minimize power only among feasible rows."""
    required = (
        "dc_gain_db",
        "dc_power_w",
        "output_dc_voltage",
        "operating_region_valid",
    )
    if any(metrics.get(name) is None for name in required):
        raise ValueError("Task 7 OP metrics are incomplete")
    local_metrics = dict(metrics)

    def lower(name: str, threshold: float, status_ok: bool = True) -> float:
        value = local_metrics.get(name)
        if value is None or not status_ok:
            return 1.0
        return max(0.0, threshold - float(value)) / max(abs(threshold), 1e-30)

    def upper(name: str, threshold: float) -> float:
        value = local_metrics.get(name)
        if value is None:
            return 1.0
        return max(0.0, float(value) - threshold) / max(abs(threshold), 1e-30)

    ugf_value = metrics.get("ugf_hz")
    ugf_ok = ugf_status == UgfStatus.MEASURED.value
    if not ugf_ok and ugf_status == UgfStatus.RIGHT_CENSORED.value:
        ugf_value = metrics.get("ugf_lower_bound_hz")
        ugf_ok = ugf_value is not None
    local_metrics["ugf_for_constraint_hz"] = ugf_value
    components = {
        "gain_min": lower("dc_gain_db", specification.gain_min_db),
        "ugf_min": (
            lower("ugf_for_constraint_hz", specification.ugf_min_hz, ugf_ok)
        ),
        "phase_margin_min": lower(
            "phase_margin_deg",
            specification.phase_margin_min_deg,
            phase_margin_status == PhaseMarginStatus.MEASURED.value,
        ),
        "power_max": upper("dc_power_w", specification.power_max_w),
        "positive_slew_min": lower(
            "positive_slew_v_per_s",
            specification.positive_slew_min_v_per_s,
            positive_slew_status == SlewStatus.MEASURED.value,
        ),
        "negative_slew_min": lower(
            "negative_slew_v_per_s",
            specification.negative_slew_min_v_per_s,
            negative_slew_status == SlewStatus.MEASURED.value,
        ),
        "output_low": lower("output_dc_voltage", specification.output_min_v),
        "output_high": upper("output_dc_voltage", specification.output_max_v),
        "operating_region": max(
            0.0, 1.0 - float(local_metrics["operating_region_valid"])
        ),
    }
    total = sum(components.values())
    power = float(local_metrics["dc_power_w"])
    secondary = power / (specification.power_max_w + max(power, 0.0))
    return Task7ObjectiveEvaluation(
        objective_value=secondary if total == 0.0 else 1.0 + total,
        constraint_violation=total,
        constraint_components=components,
        is_feasible=total == 0.0,
    )
