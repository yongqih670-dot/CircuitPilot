"""Strict, optimizer-independent configuration for research experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

import yaml

from circuitpilot.common_source import (
    COMMON_SOURCE_PARAMETER_NAMES,
    CommonSourceCircuitConfig,
    common_source_config_from_mapping,
)
from circuitpilot.exceptions import ConfigError
from circuitpilot.sky130_common_source import (
    SKY130_COMMON_SOURCE_PARAMETER_NAMES,
    Sky130CommonSourceCircuitConfig,
    sky130_common_source_config_from_mapping,
)
from circuitpilot.sky130_differential_amplifier import (
    SKY130_DIFFERENTIAL_PARAMETER_NAMES,
    Sky130DifferentialAmplifierCircuitConfig,
    sky130_differential_config_from_mapping,
)
from circuitpilot.sky130_two_stage_ota import (
    TASK7_PARAMETER_NAMES,
    Sky130TwoStageOtaCircuitConfig,
    sky130_two_stage_ota_config_from_mapping,
)


ParameterValue = float | int | str | bool
RC_METRIC_DEFINITIONS = {
    "bandwidth": "interpolated -3 dB cutoff from parsed real ngspice AC output",
    "sample_count": "number of parsed ngspice AC samples",
}
COMMON_SOURCE_METRIC_DEFINITIONS = {
    "gain_db": "low-frequency magnitude gain from parsed real ngspice AC output",
    "bandwidth_hz": "interpolated post-peak -3 dB bandwidth from parsed real ngspice AC output",
    "dc_power_w": "abs(VDD * I(VDD)) from parsed real ngspice operating-point output",
    "output_dc_voltage": "V(out) from parsed real ngspice operating-point output",
}
SKY130_COMMON_SOURCE_METRIC_DEFINITIONS = {
    "gain_db": "low-frequency gain from parsed real SKY130 ngspice AC output",
    "peak_gain_db": "peak gain from parsed real SKY130 ngspice AC output",
    "bandwidth_hz": "exact post-peak -3 dB crossing or null when right-censored",
    "bandwidth_lower_bound_hz": "fixed f_stop lower bound only when right-censored",
    "dc_power_w": "abs(VDD * I(VDD)) from parsed real SKY130 ngspice operating point",
    "output_dc_voltage": "V(out) from parsed real SKY130 ngspice operating point",
    "operating_region_valid": "1 iff VGS > VTH and VDS >= VGS - VTH from real MOS OP vectors",
}
SKY130_DIFFERENTIAL_METRIC_DEFINITIONS = {
    "differential_gain_db": "direct low-frequency gain from the opposed-input AC testbench",
    "common_mode_gain_db": "direct low-frequency gain from the equal-input AC testbench",
    "cmrr_db": "exact Ad(dB)-Acm(dB), null when common-mode gain is below the reliable floor",
    "cmrr_lower_bound_db": "conservative CMRR lower bound when common-mode gain is below the frozen floor",
    "bandwidth_hz": "exact differential post-peak -3 dB crossing or null when right-censored",
    "bandwidth_lower_bound_hz": "fixed f_stop lower bound only when differential bandwidth is right-censored",
    "dc_power_w": "abs(VDD * I(VDD)) from the differential-copy real SKY130 operating point",
    "output_dc_voltage": "V(out) from the differential-copy real SKY130 operating point",
    "tail_current_a": "absolute current through the differential-copy zero-volt tail sense source",
    "operating_region_valid": "1 iff every critical NMOS/PMOS passes its explicit voltage inequality",
}
SKY130_TWO_STAGE_OTA_METRIC_DEFINITIONS = {
    "dc_gain_db": "low-frequency gain from the unit-differential real SKY130 AC response",
    "ugf_hz": "first descending 0 dB crossing interpolated on log frequency",
    "ugf_lower_bound_hz": "f_stop lower bound only for right-censored UGF",
    "phase_margin_deg": "180 degrees plus unwrapped phase at the same first UGF",
    "minus_3db_bandwidth_hz": "optional post-peak -3 dB crossing",
    "dc_power_w": "abs(VDD * I(VDD)) from the independent real SKY130 OP process",
    "supply_current_a": "absolute VDD source current from the independent OP process",
    "output_dc_voltage": "V(vout) from the independent OP process",
    "stage1_dc_voltage": "V(stage1_out) from the independent OP process",
    "positive_slew_v_per_s": "fixed 20-80 percent rising output crossing slope",
    "negative_slew_v_per_s": "fixed 80-20 percent falling output crossing magnitude",
    "operating_region_valid": "1 iff all seven MOS devices satisfy explicit saturation inequalities",
}


class ParameterType(str, Enum):
    """Search-space parameter types supported by the baseline framework."""

    FLOAT = "float"
    INTEGER = "int"
    CATEGORICAL = "categorical"


class ObjectiveType(str, Enum):
    """Directions supported by the common objective evaluator."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"
    TARGET = "target"


class ConstraintOperator(str, Enum):
    """Scalar inequality directions supported by research constraints."""

    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="


def _finite_number(value: Any, context: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{context} must be a number")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{context} must be a number") from None
    if not isfinite(parsed):
        raise ValueError(f"{context} must be finite")
    return parsed


def _positive_number(value: Any, context: str) -> float:
    parsed = _finite_number(value, context)
    if parsed <= 0:
        raise ValueError(f"{context} must be positive")
    return parsed


def _positive_integer(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{context} must be a positive integer")
    return value


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{context} must be a YAML mapping")
    if not all(isinstance(key, str) for key in value):
        raise ConfigError(f"{context} keys must be strings")
    return value


def _keys(
    value: Mapping[str, Any], *, required: set[str], optional: set[str] | None = None,
    context: str,
) -> None:
    allowed = required | (optional or set())
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise ConfigError(f"{context} is missing required field(s): {', '.join(missing)}")
    if unknown:
        raise ConfigError(f"{context} contains unknown field(s): {', '.join(unknown)}")


@dataclass(frozen=True, slots=True)
class SearchParameter:
    """One validated search-space dimension."""

    name: str
    parameter_type: ParameterType
    low: float | None = None
    high: float | None = None
    log: bool = False
    choices: tuple[ParameterValue, ...] = ()
    unit: str | None = None
    technology_low: float | None = None
    technology_high: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("search parameter name must be non-empty")
        if not isinstance(self.parameter_type, ParameterType):
            raise ValueError("search parameter type is invalid")
        if self.parameter_type is ParameterType.CATEGORICAL:
            if (
                self.low is not None
                or self.high is not None
                or self.log
                or self.technology_low is not None
                or self.technology_high is not None
            ):
                raise ValueError(f"categorical search_space.{self.name} accepts only choices")
            if len(self.choices) < 2 or len(set(self.choices)) != len(self.choices):
                raise ValueError(
                    f"search_space.{self.name}.choices must contain at least two unique values"
                )
            for choice in self.choices:
                if not isinstance(choice, (str, int, float, bool)):
                    raise ValueError(f"search_space.{self.name}.choices must be JSON scalars")
                if isinstance(choice, float) and not isfinite(choice):
                    raise ValueError(f"search_space.{self.name}.choices must be finite")
            return
        if self.unit is not None and (not isinstance(self.unit, str) or not self.unit.strip()):
            raise ValueError(f"search_space.{self.name}.unit must be null or non-empty")
        if self.choices:
            raise ValueError(f"numeric search_space.{self.name} cannot define choices")
        if self.low is None or self.high is None:
            raise ValueError(f"search_space.{self.name} requires low and high")
        _finite_number(self.low, f"search_space.{self.name}.low")
        _finite_number(self.high, f"search_space.{self.name}.high")
        if self.high <= self.low:
            raise ValueError(f"search_space.{self.name}.high must exceed low")
        if not isinstance(self.log, bool):
            raise ValueError(f"search_space.{self.name}.log must be a boolean")
        if self.log and self.low <= 0:
            raise ValueError(f"search_space.{self.name}.low must be positive for log sampling")
        if self.parameter_type is ParameterType.INTEGER:
            if not float(self.low).is_integer() or not float(self.high).is_integer():
                raise ValueError(f"integer search_space.{self.name} bounds must be integers")
        if (self.technology_low is None) != (self.technology_high is None):
            raise ValueError(
                f"search_space.{self.name}.technology_limits requires low and high"
            )
        if self.technology_low is not None and self.technology_high is not None:
            technology_low = _finite_number(
                self.technology_low, f"search_space.{self.name}.technology_limits.low"
            )
            technology_high = _finite_number(
                self.technology_high, f"search_space.{self.name}.technology_limits.high"
            )
            if technology_high <= technology_low:
                raise ValueError(
                    f"search_space.{self.name}.technology_limits.high must exceed low"
                )
            if self.low < technology_low or self.high > technology_high:
                raise ValueError(
                    f"search_space.{self.name} exceeds declared technology limits"
                )

    def contains(self, value: Any) -> bool:
        """Return whether ``value`` is a valid member of this dimension."""
        if self.parameter_type is ParameterType.CATEGORICAL:
            return value in self.choices
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        numeric = float(value)
        assert self.low is not None and self.high is not None
        if not isfinite(numeric) or not self.low <= numeric <= self.high:
            return False
        return self.parameter_type is ParameterType.FLOAT or numeric.is_integer()

    def to_dict(self) -> dict[str, Any]:
        """Return a stable YAML-compatible dimension definition."""
        if self.parameter_type is ParameterType.CATEGORICAL:
            return {"type": self.parameter_type.value, "choices": list(self.choices)}
        result = {
            "type": self.parameter_type.value,
            "low": self.low,
            "high": self.high,
            "log": self.log,
        }
        if self.unit is not None:
            result["unit"] = self.unit
        if self.technology_low is not None and self.technology_high is not None:
            result["technology_limits"] = {
                "low": self.technology_low,
                "high": self.technology_high,
            }
        return result


@dataclass(frozen=True, slots=True)
class ObjectiveDefinition:
    metric: str
    objective_type: ObjectiveType
    target: float | None = None
    weight: float = 1.0
    frequency_hz: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.metric, str) or not self.metric.strip():
            raise ValueError("objective metric name must be non-empty")
        if not isinstance(self.objective_type, ObjectiveType):
            raise ValueError("objective type is invalid")
        _positive_number(self.weight, f"objectives.{self.metric}.weight")
        if self.objective_type is ObjectiveType.TARGET:
            if self.target is None:
                raise ValueError(f"target objective '{self.metric}' requires target")
            _finite_number(self.target, f"objectives.{self.metric}.target")
        elif self.target is not None:
            raise ValueError(f"objective '{self.metric}' only accepts target when type is target")
        if self.frequency_hz is not None:
            _positive_number(self.frequency_hz, f"objectives.{self.metric}.frequency_hz")


@dataclass(frozen=True, slots=True)
class ConstraintDefinition:
    metric: str
    operator: ConstraintOperator
    threshold: float
    frequency_hz: float | None = None
    constraint_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.metric, str) or not self.metric.strip():
            raise ValueError("constraint metric name must be non-empty")
        if not isinstance(self.operator, ConstraintOperator):
            raise ValueError("constraint operator is invalid")
        _finite_number(self.threshold, f"constraints.{self.metric}.threshold")
        if self.frequency_hz is not None:
            _positive_number(self.frequency_hz, f"constraints.{self.metric}.frequency_hz")
        if self.constraint_id is not None and (
            not isinstance(self.constraint_id, str) or not self.constraint_id.strip()
        ):
            raise ValueError("constraint_id must be null or non-empty")


@dataclass(frozen=True, slots=True)
class SuccessCriterion:
    """Shared, method-independent definition of a feasible design."""

    metric: str | None = "bandwidth"
    relative_error_threshold: float | None = 0.05
    criterion_type: str = "target_relative_error"

    def __post_init__(self) -> None:
        if self.criterion_type not in {"target_relative_error", "all_constraints"}:
            raise ValueError(
                "success_criterion.type must be target_relative_error or all_constraints"
            )
        if self.criterion_type == "all_constraints":
            if self.metric is not None or self.relative_error_threshold is not None:
                raise ValueError(
                    "all_constraints success criterion cannot define metric or relative_error_threshold"
                )
            return
        if not isinstance(self.metric, str) or not self.metric.strip():
            raise ValueError("success_criterion.metric must be non-empty")
        threshold = _positive_number(
            self.relative_error_threshold, "success_criterion.relative_error_threshold"
        )
        if threshold > 1:
            raise ValueError("success_criterion.relative_error_threshold must not exceed 1")


@dataclass(frozen=True, slots=True)
class NgspiceConfig:
    executable: str = "ngspice"
    start_frequency_hz: float = 10.0
    stop_frequency_hz: float = 10_000_000.0
    points_per_decade: int = 50

    def __post_init__(self) -> None:
        if not isinstance(self.executable, str) or not self.executable.strip():
            raise ValueError("ngspice_config.executable must be non-empty")
        _positive_number(self.start_frequency_hz, "ngspice_config.start_frequency_hz")
        _positive_number(self.stop_frequency_hz, "ngspice_config.stop_frequency_hz")
        if self.stop_frequency_hz <= self.start_frequency_hz:
            raise ValueError("ngspice_config.stop_frequency_hz must exceed start_frequency_hz")
        if isinstance(self.points_per_decade, bool) or not isinstance(self.points_per_decade, int) or self.points_per_decade < 2:
            raise ValueError("ngspice_config.points_per_decade must be at least 2")


OPTIMIZER_DEFAULTS: dict[str, dict[str, Any]] = {
    "random": {},
    "de": {
        "population_size": 8,
        "mutation": 0.8,
        "recombination": 0.7,
        "strategy": "best1bin",
    },
    "tpe": {"n_startup_trials": 5, "multivariate": False},
    "bo": {
        "initial_random_points": 5,
        "candidate_pool_size": 512,
        "exploration_xi": 0.01,
        "noise": 1e-8,
    },
}


def _resolved_optimizer_config(method: str, value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate method hyperparameters while keeping one config entry point."""
    if method not in OPTIMIZER_DEFAULTS:
        if value:
            raise ValueError(f"custom optimizer method '{method}' cannot define optimizer_config")
        return {}
    allowed = set(OPTIMIZER_DEFAULTS[method])
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{method} optimizer_config contains unknown field(s): {', '.join(unknown)}")
    result = {**OPTIMIZER_DEFAULTS[method], **dict(value)}
    if method == "de":
        if _positive_integer(result["population_size"], "optimizer_config.population_size") < 4:
            raise ValueError("optimizer_config.population_size must be at least 4")
        mutation = _positive_number(result["mutation"], "optimizer_config.mutation")
        if mutation > 2:
            raise ValueError("optimizer_config.mutation must not exceed 2")
        recombination = _finite_number(result["recombination"], "optimizer_config.recombination")
        if not 0 <= recombination <= 1:
            raise ValueError("optimizer_config.recombination must be between 0 and 1")
        if result["strategy"] not in {"best1bin", "rand1bin"}:
            raise ValueError("optimizer_config.strategy must be best1bin or rand1bin")
    elif method == "tpe":
        _positive_integer(result["n_startup_trials"], "optimizer_config.n_startup_trials")
        if not isinstance(result["multivariate"], bool):
            raise ValueError("optimizer_config.multivariate must be a boolean")
    elif method == "bo":
        _positive_integer(result["initial_random_points"], "optimizer_config.initial_random_points")
        if _positive_integer(result["candidate_pool_size"], "optimizer_config.candidate_pool_size") < 16:
            raise ValueError("optimizer_config.candidate_pool_size must be at least 16")
        if _finite_number(result["exploration_xi"], "optimizer_config.exploration_xi") < 0:
            raise ValueError("optimizer_config.exploration_xi must be non-negative")
        _positive_number(result["noise"], "optimizer_config.noise")
    return result


@dataclass(frozen=True, slots=True)
class ExperimentConfig:
    """Single source of truth shared by every research optimization method."""

    experiment_name: str
    circuit_name: str
    method: str
    seed: int
    simulation_budget: int
    output_dir: Path
    search_space: tuple[SearchParameter, ...]
    objectives: tuple[ObjectiveDefinition, ...]
    constraints: tuple[ConstraintDefinition, ...] = ()
    success_criterion: SuccessCriterion = SuccessCriterion()
    optimizer_config: Mapping[str, Any] = field(default_factory=dict)
    ngspice_config: NgspiceConfig = NgspiceConfig()
    pvt_config: Mapping[str, Any] = field(default_factory=dict)
    circuit_config: (
        CommonSourceCircuitConfig
        | Sky130CommonSourceCircuitConfig
        | Sky130DifferentialAmplifierCircuitConfig
        | Sky130TwoStageOtaCircuitConfig
        | None
    ) = None
    benchmark_config_hash: str | None = None
    experiment_phase: str = "baseline"
    resume: bool = False
    timeout: float = 60.0

    def __post_init__(self) -> None:
        if not isinstance(self.experiment_name, str) or not self.experiment_name.strip():
            raise ValueError("experiment_name must be non-empty")
        if self.circuit_name not in {
            "rc_lowpass",
            "common_source",
            "sky130_common_source",
            "sky130_differential_amplifier",
            "sky130_two_stage_ota",
        }:
            raise ValueError(
                "unsupported research circuit"
            )
        if not isinstance(self.method, str) or not self.method.strip():
            raise ValueError("method must be non-empty")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        _positive_integer(self.simulation_budget, "simulation_budget")
        if not isinstance(self.output_dir, Path):
            raise ValueError("output_dir must be a pathlib.Path")
        if not self.search_space or not all(isinstance(item, SearchParameter) for item in self.search_space):
            raise ValueError("search_space must contain SearchParameter objects")
        names = [item.name for item in self.search_space]
        if len(set(names)) != len(names):
            raise ValueError("search_space parameter names must be unique")
        expected_parameters = {
            "rc_lowpass": {"resistance", "capacitance"},
            "common_source": COMMON_SOURCE_PARAMETER_NAMES,
            "sky130_common_source": SKY130_COMMON_SOURCE_PARAMETER_NAMES,
            "sky130_differential_amplifier": SKY130_DIFFERENTIAL_PARAMETER_NAMES,
            "sky130_two_stage_ota": TASK7_PARAMETER_NAMES,
        }[self.circuit_name]
        if set(names) != expected_parameters:
            readable = ", ".join(sorted(expected_parameters))
            raise ValueError(
                f"{self.circuit_name} search_space must contain exactly: {readable}"
            )
        if self.circuit_name in {
            "common_source",
            "sky130_common_source",
            "sky130_differential_amplifier",
            "sky130_two_stage_ota",
        }:
            for parameter in self.search_space:
                if parameter.unit is None:
                    raise ValueError(
                        f"common_source search_space.{parameter.name} requires unit"
                    )
                if parameter.technology_low is None or parameter.technology_high is None:
                    raise ValueError(
                        f"common_source search_space.{parameter.name} requires technology_limits"
                    )
        if not self.objectives or not all(isinstance(item, ObjectiveDefinition) for item in self.objectives):
            raise ValueError("objectives must contain ObjectiveDefinition objects")
        if len({item.metric for item in self.objectives}) != len(self.objectives):
            raise ValueError("objective metric names must be unique")
        if not all(isinstance(item, ConstraintDefinition) for item in self.constraints):
            raise ValueError("constraints must contain ConstraintDefinition objects")
        constraint_ids = [item.constraint_id or item.metric for item in self.constraints]
        if len(set(constraint_ids)) != len(constraint_ids):
            raise ValueError("constraint identifiers must be unique")
        if not isinstance(self.success_criterion, SuccessCriterion):
            raise ValueError("success_criterion must be SuccessCriterion")
        targets = {
            item.metric: item.target for item in self.objectives
            if item.objective_type is ObjectiveType.TARGET
        }
        if self.success_criterion.criterion_type == "target_relative_error":
            if self.success_criterion.metric not in targets:
                raise ValueError("success_criterion.metric must name a target objective")
        elif not self.constraints:
            raise ValueError("all_constraints success criterion requires constraints")
        if not isinstance(self.optimizer_config, Mapping):
            raise ValueError("optimizer_config must be a mapping")
        forbidden = {"seed", "random_seed", "random_state", "sampler_seed"}
        duplicated = sorted(forbidden & set(self.optimizer_config))
        if duplicated:
            raise ValueError("ExperimentConfig.seed is the only seed entry; remove optimizer_config " + ", ".join(duplicated))
        resolved = _resolved_optimizer_config(self.method, self.optimizer_config)
        object.__setattr__(self, "optimizer_config", resolved)
        if not isinstance(self.ngspice_config, NgspiceConfig):
            raise ValueError("ngspice_config must be NgspiceConfig")
        if not isinstance(self.pvt_config, Mapping) or self.pvt_config:
            raise ValueError("the non-PVT research baselines require an explicit empty pvt_config")
        if self.circuit_name == "common_source":
            if not isinstance(self.circuit_config, CommonSourceCircuitConfig):
                raise ValueError("common_source requires a typed circuit_config")
            self.circuit_config.model.require_library()
        elif self.circuit_name == "sky130_common_source":
            if not isinstance(self.circuit_config, Sky130CommonSourceCircuitConfig):
                raise ValueError(
                    "sky130_common_source requires a typed SKY130 circuit_config"
                )
            if self.circuit_config.model.expected_model_sha256 is None:
                raise ValueError("Task 4 circuit_config must bind model_sha256")
            if self.circuit_config.model.expected_library_sha256 is None:
                raise ValueError("Task 4 circuit_config must bind library_sha256")
        elif self.circuit_name == "sky130_differential_amplifier":
            if not isinstance(
                self.circuit_config, Sky130DifferentialAmplifierCircuitConfig
            ):
                raise ValueError(
                    "sky130_differential_amplifier requires a typed SKY130 circuit_config"
                )
            if self.circuit_config.model.expected_model_sha256 is None:
                raise ValueError("Task 5 circuit_config must bind model_sha256")
            if self.circuit_config.model.expected_library_sha256 is None:
                raise ValueError("Task 5 circuit_config must bind library_sha256")
        elif self.circuit_name == "sky130_two_stage_ota":
            if not isinstance(self.circuit_config, Sky130TwoStageOtaCircuitConfig):
                raise ValueError(
                    "sky130_two_stage_ota requires a typed SKY130 circuit_config"
                )
            if self.circuit_config.model.expected_model_sha256 is None:
                raise ValueError("Task 7 circuit_config must bind model_sha256")
            if self.circuit_config.model.expected_library_sha256 is None:
                raise ValueError("Task 7 circuit_config must bind library_sha256")
        elif self.circuit_config is not None:
            raise ValueError("rc_lowpass cannot define circuit_config")
        if self.benchmark_config_hash is not None:
            if (
                not isinstance(self.benchmark_config_hash, str)
                or len(self.benchmark_config_hash) != 64
                or any(character not in "0123456789abcdef" for character in self.benchmark_config_hash)
            ):
                raise ValueError("benchmark_config_hash must be a lowercase SHA-256 hex string")
            if self.benchmark_config_hash != self.computed_benchmark_hash():
                raise ValueError(
                    "benchmark_config_hash does not match the resolved frozen benchmark configuration"
                )
        if self.experiment_phase not in {"baseline", "smoke", "calibration"}:
            raise ValueError("experiment.phase must be baseline, smoke, or calibration")
        if not isinstance(self.resume, bool):
            raise ValueError("resume must be a boolean")
        _positive_number(self.timeout, "timeout")

    @property
    def search_space_by_name(self) -> dict[str, SearchParameter]:
        return {parameter.name: parameter for parameter in self.search_space}

    @property
    def target_by_metric(self) -> dict[str, float]:
        return {
            item.metric: float(item.target) for item in self.objectives
            if item.objective_type is ObjectiveType.TARGET and item.target is not None
        }

    def validate_parameters(self, parameters: Mapping[str, Any]) -> None:
        if not isinstance(parameters, Mapping):
            raise ValueError("candidate parameters must be a mapping")
        expected = set(self.search_space_by_name)
        actual = set(parameters)
        if actual != expected:
            missing = sorted(expected - actual)
            unknown = sorted(actual - expected)
            details = (["missing: " + ", ".join(missing)] if missing else []) + (["unknown: " + ", ".join(unknown)] if unknown else [])
            raise ValueError("invalid candidate parameter keys (" + "; ".join(details) + ")")
        for name, definition in self.search_space_by_name.items():
            if not definition.contains(parameters[name]):
                raise ValueError(f"candidate parameter '{name}' is outside its validated search space")

    def to_dict(self) -> dict[str, Any]:
        metric_definitions = {
            "rc_lowpass": RC_METRIC_DEFINITIONS,
            "common_source": COMMON_SOURCE_METRIC_DEFINITIONS,
            "sky130_common_source": SKY130_COMMON_SOURCE_METRIC_DEFINITIONS,
            "sky130_differential_amplifier": SKY130_DIFFERENTIAL_METRIC_DEFINITIONS,
            "sky130_two_stage_ota": SKY130_TWO_STAGE_OTA_METRIC_DEFINITIONS,
        }[self.circuit_name]
        result = {
            "experiment": {
                "name": self.experiment_name, "circuit": self.circuit_name,
                "method": self.method, "seed": self.seed,
                "simulation_budget": self.simulation_budget,
                "output_dir": self.output_dir.as_posix(), "resume": self.resume,
                "timeout": self.timeout, "phase": self.experiment_phase,
            },
            "search_space": {item.name: item.to_dict() for item in self.search_space},
            "objectives": {
                item.metric: {
                    "type": item.objective_type.value,
                    **({"target": item.target} if item.target is not None else {}),
                    "weight": item.weight,
                    **({"frequency_hz": item.frequency_hz} if item.frequency_hz is not None else {}),
                } for item in self.objectives
            },
            "constraints": {
                item.constraint_id or item.metric: {
                    **({"metric": item.metric} if item.constraint_id else {}),
                    "operator": item.operator.value, "threshold": item.threshold,
                    **({"frequency_hz": item.frequency_hz} if item.frequency_hz is not None else {}),
                } for item in self.constraints
            },
            "success_criterion": {
                "type": self.success_criterion.criterion_type,
                **(
                    {
                        "metric": self.success_criterion.metric,
                        "relative_error_threshold": self.success_criterion.relative_error_threshold,
                    }
                    if self.success_criterion.criterion_type == "target_relative_error"
                    else {}
                ),
            },
            "optimizer_config": dict(self.optimizer_config),
            "ngspice_config": {
                "executable": self.ngspice_config.executable,
                "start_frequency_hz": self.ngspice_config.start_frequency_hz,
                "stop_frequency_hz": self.ngspice_config.stop_frequency_hz,
                "points_per_decade": self.ngspice_config.points_per_decade,
            },
            "metric_definitions": dict(metric_definitions),
            "pvt_config": dict(self.pvt_config),
        }
        if self.circuit_config is not None:
            result["circuit_config"] = self.circuit_config.to_dict()
        if self.benchmark_config_hash is not None:
            result["benchmark_config_hash"] = self.benchmark_config_hash
        return result

    def computed_benchmark_hash(self) -> str:
        """Hash all circuit semantics shared by every benchmark method/seed."""
        metric_definitions = {
            "rc_lowpass": RC_METRIC_DEFINITIONS,
            "common_source": COMMON_SOURCE_METRIC_DEFINITIONS,
            "sky130_common_source": SKY130_COMMON_SOURCE_METRIC_DEFINITIONS,
            "sky130_differential_amplifier": SKY130_DIFFERENTIAL_METRIC_DEFINITIONS,
            "sky130_two_stage_ota": SKY130_TWO_STAGE_OTA_METRIC_DEFINITIONS,
        }[self.circuit_name]
        payload: dict[str, Any] = {
            "circuit": self.circuit_name,
            "search_space": {item.name: item.to_dict() for item in self.search_space},
            "objectives": [
                {
                    "metric": item.metric,
                    "type": item.objective_type.value,
                    "target": item.target,
                    "weight": item.weight,
                    "frequency_hz": item.frequency_hz,
                }
                for item in self.objectives
            ],
            "constraints": [
                {
                    "id": item.constraint_id or item.metric,
                    "metric": item.metric,
                    "operator": item.operator.value,
                    "threshold": item.threshold,
                    "frequency_hz": item.frequency_hz,
                }
                for item in self.constraints
            ],
            "success_criterion": {
                "type": self.success_criterion.criterion_type,
                "metric": self.success_criterion.metric,
                "relative_error_threshold": self.success_criterion.relative_error_threshold,
            },
            "ngspice_config": {
                "start_frequency_hz": self.ngspice_config.start_frequency_hz,
                "stop_frequency_hz": self.ngspice_config.stop_frequency_hz,
                "points_per_decade": self.ngspice_config.points_per_decade,
            },
            "pvt_config": dict(self.pvt_config),
            "metric_definitions": dict(metric_definitions),
        }
        if isinstance(self.circuit_config, CommonSourceCircuitConfig):
            circuit_payload = self.circuit_config.to_dict()
            circuit_payload["mosfet_model"] = dict(circuit_payload["mosfet_model"])
            circuit_payload["mosfet_model"]["model_library"] = "<content-addressed-model>"
            payload["circuit_config"] = circuit_payload
            payload["model_library_sha256"] = self.circuit_config.model.library_sha256()
        elif isinstance(self.circuit_config, Sky130CommonSourceCircuitConfig):
            circuit_payload = self.circuit_config.to_dict()
            model_payload = dict(circuit_payload["sky130_model"])
            model_payload["pdk_root"] = "<content-addressed-sky130-pdk>"
            model_payload["model_library"] = "<content-addressed-model>"
            circuit_payload["sky130_model"] = model_payload
            payload["circuit_config"] = circuit_payload
            payload["model_sha256"] = self.circuit_config.model.model_sha256()
            payload["model_library_sha256"] = self.circuit_config.model.library_sha256()
        elif isinstance(
            self.circuit_config, Sky130DifferentialAmplifierCircuitConfig
        ):
            circuit_payload = self.circuit_config.to_dict()
            model_payload = dict(circuit_payload["sky130_model"])
            model_payload["pdk_root"] = "<content-addressed-sky130-pdk>"
            model_payload["model_library"] = "<content-addressed-model>"
            circuit_payload["sky130_model"] = model_payload
            payload["circuit_config"] = circuit_payload
            payload["model_sha256"] = self.circuit_config.model.model_sha256()
            payload["model_library_sha256"] = self.circuit_config.model.library_sha256()
        elif isinstance(self.circuit_config, Sky130TwoStageOtaCircuitConfig):
            circuit_payload = self.circuit_config.to_dict()
            model_payload = dict(circuit_payload["sky130_model"])
            model_payload["pdk_root"] = "<content-addressed-sky130-pdk>"
            model_payload["model_library"] = "<content-addressed-model>"
            circuit_payload["sky130_model"] = model_payload
            payload["circuit_config"] = circuit_payload
            payload["model_sha256"] = self.circuit_config.model.model_sha256()
            payload["model_library_sha256"] = self.circuit_config.model.library_sha256()
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return sha256(encoded).hexdigest()

    def identity_sha256(self) -> str:
        payload = self.to_dict()
        payload["experiment"]["resume"] = False
        payload["experiment"]["output_dir"] = "<run-output>"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        return sha256(encoded).hexdigest()

    def resume_identity_sha256(self) -> str:
        """Hash immutable semantics while allowing only a budget extension."""
        payload = self.to_dict()
        payload["experiment"]["resume"] = False
        payload["experiment"]["output_dir"] = "<run-output>"
        payload["experiment"]["simulation_budget"] = "<extendable-budget>"
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        return sha256(encoded).hexdigest()

    def search_space_sha256(self) -> str:
        payload = {item.name: item.to_dict() for item in self.search_space}
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _parse_search_space(value: Any) -> tuple[SearchParameter, ...]:
    mapping = _mapping(value, "search_space")
    parameters: list[SearchParameter] = []
    for name, raw in mapping.items():
        definition = _mapping(raw, f"search_space.{name}")
        try:
            parameter_type = ParameterType(definition.get("type"))
        except (TypeError, ValueError):
            raise ConfigError(f"search_space.{name}.type must be float, int, or categorical") from None
        if parameter_type is ParameterType.CATEGORICAL:
            _keys(
                definition,
                required={"type", "choices"},
                optional={"unit"},
                context=f"search_space.{name}",
            )
            raw_choices = definition["choices"]
            if not isinstance(raw_choices, list):
                raise ConfigError(f"search_space.{name}.choices must be a YAML list")
            arguments = {
                "name": name,
                "parameter_type": parameter_type,
                "choices": tuple(raw_choices),
                "unit": definition.get("unit"),
            }
        else:
            _keys(
                definition,
                required={"type", "low", "high"},
                optional={"log", "unit", "technology_limits"},
                context=f"search_space.{name}",
            )
            technology_limits = definition.get("technology_limits")
            if technology_limits is not None:
                technology_limits = _mapping(
                    technology_limits, f"search_space.{name}.technology_limits"
                )
                _keys(
                    technology_limits,
                    required={"low", "high"},
                    context=f"search_space.{name}.technology_limits",
                )
            arguments = {
                "name": name, "parameter_type": parameter_type,
                "low": _finite_number(definition["low"], f"search_space.{name}.low"),
                "high": _finite_number(definition["high"], f"search_space.{name}.high"),
                "log": definition.get("log", False),
                "unit": definition.get("unit"),
                "technology_low": (
                    None
                    if technology_limits is None
                    else _finite_number(
                        technology_limits["low"],
                        f"search_space.{name}.technology_limits.low",
                    )
                ),
                "technology_high": (
                    None
                    if technology_limits is None
                    else _finite_number(
                        technology_limits["high"],
                        f"search_space.{name}.technology_limits.high",
                    )
                ),
            }
        try:
            parameters.append(SearchParameter(**arguments))
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
    return tuple(parameters)


def _parse_objectives(value: Any) -> tuple[ObjectiveDefinition, ...]:
    mapping = _mapping(value, "objectives")
    result = []
    for metric, raw in mapping.items():
        definition = _mapping(raw, f"objectives.{metric}")
        _keys(definition, required={"type"}, optional={"target", "weight", "frequency_hz"}, context=f"objectives.{metric}")
        try:
            kind = ObjectiveType(definition["type"])
            result.append(ObjectiveDefinition(
                metric=metric, objective_type=kind,
                target=None if "target" not in definition else _finite_number(definition["target"], f"objectives.{metric}.target"),
                weight=_positive_number(definition.get("weight", 1.0), f"objectives.{metric}.weight"),
                frequency_hz=None if "frequency_hz" not in definition else _positive_number(definition["frequency_hz"], f"objectives.{metric}.frequency_hz"),
            ))
        except (TypeError, ValueError) as exc:
            raise ConfigError(str(exc)) from exc
    return tuple(result)


def _parse_constraints(value: Any) -> tuple[ConstraintDefinition, ...]:
    mapping = _mapping(value, "constraints")
    result = []
    for constraint_id, raw in mapping.items():
        definition = _mapping(raw, f"constraints.{constraint_id}")
        _keys(
            definition,
            required={"operator", "threshold"},
            optional={"metric", "frequency_hz"},
            context=f"constraints.{constraint_id}",
        )
        metric = definition.get("metric", constraint_id)
        try:
            result.append(ConstraintDefinition(
                metric=metric, operator=ConstraintOperator(definition["operator"]),
                threshold=_finite_number(definition["threshold"], f"constraints.{metric}.threshold"),
                frequency_hz=None if "frequency_hz" not in definition else _positive_number(definition["frequency_hz"], f"constraints.{metric}.frequency_hz"),
                constraint_id=(constraint_id if metric != constraint_id else None),
            ))
        except (TypeError, ValueError) as exc:
            raise ConfigError(str(exc)) from exc
    return tuple(result)


def _parse_ngspice_config(value: Any) -> NgspiceConfig:
    mapping = _mapping(value, "ngspice_config")
    _keys(mapping, required=set(), optional={"executable", "start_frequency_hz", "stop_frequency_hz", "points_per_decade"}, context="ngspice_config")
    try:
        return NgspiceConfig(
            executable=mapping.get("executable", "ngspice"),
            start_frequency_hz=_positive_number(mapping.get("start_frequency_hz", 10.0), "ngspice_config.start_frequency_hz"),
            stop_frequency_hz=_positive_number(mapping.get("stop_frequency_hz", 10_000_000.0), "ngspice_config.stop_frequency_hz"),
            points_per_decade=mapping.get("points_per_decade", 50),
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def _parse_success(value: Any) -> SuccessCriterion:
    mapping = _mapping(value, "success_criterion")
    criterion_type = mapping.get("type", "target_relative_error")
    if criterion_type == "all_constraints":
        _keys(mapping, required={"type"}, context="success_criterion")
        try:
            return SuccessCriterion(
                metric=None,
                relative_error_threshold=None,
                criterion_type="all_constraints",
            )
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
    _keys(
        mapping,
        required={"metric", "relative_error_threshold"},
        optional={"type"},
        context="success_criterion",
    )
    try:
        return SuccessCriterion(
            metric=mapping["metric"],
            relative_error_threshold=_positive_number(mapping["relative_error_threshold"], "success_criterion.relative_error_threshold"),
            criterion_type=criterion_type,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def experiment_config_from_mapping(
    value: Mapping[str, Any], *, base_directory: Path | None = None
) -> ExperimentConfig:
    root = _mapping(value, "configuration root")
    _keys(
        root,
        required={"experiment", "search_space", "objectives"},
        optional={
            "constraints",
            "success_criterion",
            "optimizer_config",
            "ngspice_config",
            "metric_definitions",
            "pvt_config",
            "circuit_config",
            "benchmark_config_hash",
        },
        context="configuration root",
    )
    experiment = _mapping(root["experiment"], "experiment")
    _keys(
        experiment,
        required={"name", "circuit", "method", "seed", "simulation_budget"},
        optional={"output_dir", "resume", "timeout", "phase"},
        context="experiment",
    )
    optimizer_config = _mapping(root.get("optimizer_config", {}), "optimizer_config")
    pvt_config = _mapping(root.get("pvt_config", {}), "pvt_config")
    circuit_name = experiment["circuit"]
    try:
        expected_metric_definitions = {
            "rc_lowpass": RC_METRIC_DEFINITIONS,
            "common_source": COMMON_SOURCE_METRIC_DEFINITIONS,
            "sky130_common_source": SKY130_COMMON_SOURCE_METRIC_DEFINITIONS,
            "sky130_differential_amplifier": SKY130_DIFFERENTIAL_METRIC_DEFINITIONS,
            "sky130_two_stage_ota": SKY130_TWO_STAGE_OTA_METRIC_DEFINITIONS,
        }[circuit_name]
    except KeyError:
        raise ConfigError(
            "experiment.circuit is unsupported"
        ) from None
    metric_definitions = _mapping(
        root.get("metric_definitions", expected_metric_definitions), "metric_definitions"
    )
    if dict(metric_definitions) != expected_metric_definitions:
        raise ConfigError(
            f"metric_definitions must match the audited {circuit_name} analyzer"
        )
    try:
        objectives = _parse_objectives(root["objectives"])
        default_success_metric = next((item.metric for item in objectives if item.objective_type is ObjectiveType.TARGET), "bandwidth")
        success = _parse_success(root["success_criterion"]) if "success_criterion" in root else SuccessCriterion(default_success_metric, 0.05)
        return ExperimentConfig(
            experiment_name=experiment["name"], circuit_name=circuit_name,
            method=experiment["method"], seed=experiment["seed"],
            simulation_budget=_positive_integer(experiment["simulation_budget"], "experiment.simulation_budget"),
            output_dir=Path(experiment.get("output_dir", "research_runs")),
            search_space=_parse_search_space(root["search_space"]), objectives=objectives,
            constraints=_parse_constraints(root.get("constraints", {})), success_criterion=success,
            optimizer_config=dict(optimizer_config), ngspice_config=_parse_ngspice_config(root.get("ngspice_config", {})),
            pvt_config=dict(pvt_config), resume=experiment.get("resume", False),
            timeout=_positive_number(experiment.get("timeout", 60.0), "experiment.timeout"),
            circuit_config=(
                common_source_config_from_mapping(
                    root.get("circuit_config"), base_directory=base_directory
                )
                if circuit_name == "common_source"
                else (
                    sky130_common_source_config_from_mapping(
                        root.get("circuit_config"), base_directory=base_directory
                    )
                    if circuit_name == "sky130_common_source"
                    else (
                        sky130_differential_config_from_mapping(
                            root.get("circuit_config"), base_directory=base_directory
                        )
                        if circuit_name == "sky130_differential_amplifier"
                        else (
                            sky130_two_stage_ota_config_from_mapping(
                                root.get("circuit_config"),
                                base_directory=base_directory,
                            )
                            if circuit_name == "sky130_two_stage_ota"
                            else None
                        )
                    )
                )
            ),
            benchmark_config_hash=root.get("benchmark_config_hash"),
            experiment_phase=experiment.get("phase", "baseline"),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(str(exc)) from exc


def load_experiment_config(config_path: str | Path) -> ExperimentConfig:
    source = Path(config_path).resolve()
    try:
        text = source.read_text(encoding="utf-8", errors="strict")
        loaded = yaml.safe_load(text)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"failed to read experiment config '{source}': {exc}") from exc
    return experiment_config_from_mapping(
        _mapping(loaded, "configuration root"), base_directory=source.parent
    )


def write_experiment_config(config: ExperimentConfig, path: str | Path) -> Path:
    destination = Path(path).resolve()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(yaml.safe_dump(config.to_dict(), sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"failed to write resolved experiment config '{destination}': {exc}") from exc
    return destination
