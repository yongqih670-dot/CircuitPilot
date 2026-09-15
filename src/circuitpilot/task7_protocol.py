"""Frozen search, specification, objective, and fairness helpers for Task 7."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from math import isfinite, log10
from typing import Any, Mapping, Sequence

from circuitpilot.sky130_two_stage_ota import (
    DEVICE_ROLE_MAPPING,
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
TASK7_COMPONENT_HASHES = {
    "topology_hash": "75f3ed595af347524d7e1d74290980f7c75ae9f503559ca561da7cd349303e6c",
    "role_mapping_hash": "50b2fe35a92fb3e56e804d9cc2ac641b9f7044198dccbd286360ef4378d48e5f",
    "pdk_hash": "d88fa42b4f42f7b1f6987141aa92161865cfc9ff5fbdce9bbc9f137bde3a2f61",
    "model_library_hash": "17c208a699228f5acb87bf59c09c22a4c4d3937b6766b4957737d34e8e075f64",
    "ugf_semantics_hash": "5f0bd2d5795ddbba88580c8de2a44788a0b12857b6232be70272881ded8f3852",
    "phase_margin_semantics_hash": (
        "68b5a1ed0cddd1efd884e75c05c01d60cdfc20b640198cd1fc88dfc119031c1b"
    ),
    "transient_semantics_hash": "b7aa31978b2e3264373f0f6cafda4305bca1c7b96daa7483668ddb57616a52fb",
    "slew_semantics_hash": "aadac51099130757f0d3774b2926801023ccc3ef00a933c99e7586d83f1b1839",
    "load_testbench_hash": "8bd34b09ff751c15a89dedf0967f1fd73434034fb38336593fb3c5e2384e555c",
    "cost_model_hash": "1a48c49e8aeb3b3f9e62a0535d33020b2c3b5600d53111417ad65d2379a89845",
    "objective_hash": "6c8bfb8a99b80dfe507c76fa191f03225694b0ff5f43818495dde4c78a5cd6b1",
}

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


def task7_component_hashes(config: Any) -> dict[str, str]:
    """Compute every individually named Task 7 fairness component."""
    circuit = config.circuit_config
    if circuit is None:
        raise ValueError("Task 7 component hashes require a circuit configuration")
    payload = circuit.to_dict()
    return {
        "topology_hash": stable_hash(
            {
                "version": circuit.topology_version,
                "definition": payload["topology_definition"],
            }
        ),
        "role_mapping_hash": stable_hash(
            {
                "version": circuit.device_role_mapping_version,
                "mapping": DEVICE_ROLE_MAPPING,
            }
        ),
        "pdk_hash": circuit.model.model_sha256(),
        "model_library_hash": circuit.model.library_sha256(),
        "ugf_semantics_hash": stable_hash(circuit.ugf_semantics_version),
        "phase_margin_semantics_hash": stable_hash(
            circuit.phase_margin_semantics_version
        ),
        "transient_semantics_hash": stable_hash(
            {
                "version": circuit.transient_testbench_version,
                "low_v": circuit.transient_low_v,
                "high_v": circuit.transient_high_v,
                "rising_edge_s": circuit.transient_rising_edge_s,
                "falling_edge_s": circuit.transient_falling_edge_s,
                "stop_s": circuit.transient_stop_time_s,
                "max_step_s": circuit.transient_max_step_s,
            }
        ),
        "slew_semantics_hash": stable_hash(
            {
                "version": circuit.slew_semantics_version,
                "lower_fraction": circuit.slew_lower_fraction,
                "upper_fraction": circuit.slew_upper_fraction,
                "edge_exclusion_s": circuit.transient_edge_exclusion_s,
            }
        ),
        "load_testbench_hash": stable_hash(
            {
                "supply_v": circuit.supply_voltage_v,
                "input_common_mode_v": circuit.input_common_mode_v,
                "tail_bias_v": circuit.tail_bias_v,
                "load_capacitance_f": circuit.load_capacitance_f,
                "temperature_c": circuit.temperature_c,
                "ac_testbench_version": circuit.ac_testbench_version,
            }
        ),
        "cost_model_hash": stable_hash(
            {
                "version": circuit.cost_semantics_version,
                "definition": payload["cost_definition"],
            }
        ),
        "objective_hash": stable_hash(
            {
                "version": OBJECTIVE_SEMANTICS_VERSION,
                "objectives": [
                    {
                        "metric": item.metric,
                        "type": item.objective_type.value,
                        "weight": item.weight,
                    }
                    for item in config.objectives
                ],
                "constraints": [
                    {
                        "id": item.constraint_id or item.metric,
                        "metric": item.metric,
                        "operator": item.operator.value,
                        "threshold": item.threshold,
                    }
                    for item in config.constraints
                ],
            }
        ),
    }


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
