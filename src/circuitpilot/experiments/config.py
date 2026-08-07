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

from circuitpilot.exceptions import ConfigError


class ParameterType(str, Enum):
    """Search-space parameter types supported by the baseline framework."""

    FLOAT = "float"
    INTEGER = "int"


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
    """Convert one YAML value to a finite floating-point number."""
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
    """Convert one YAML value to a finite positive number."""
    parsed = _finite_number(value, context)
    if parsed <= 0:
        raise ValueError(f"{context} must be positive")
    return parsed


def _positive_integer(value: Any, context: str) -> int:
    """Require a positive non-boolean integer."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{context} must be a positive integer")
    return value


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    """Require a YAML mapping with string keys."""
    if not isinstance(value, Mapping):
        raise ConfigError(f"{context} must be a YAML mapping")
    if not all(isinstance(key, str) for key in value):
        raise ConfigError(f"{context} keys must be strings")
    return value


def _keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
    context: str,
) -> None:
    """Reject missing fields and spelling mistakes."""
    allowed = required | (optional or set())
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise ConfigError(f"{context} is missing required field(s): {', '.join(missing)}")
    if unknown:
        raise ConfigError(f"{context} contains unknown field(s): {', '.join(unknown)}")


@dataclass(frozen=True, slots=True)
class SearchParameter:
    """One validated scalar search-space dimension."""

    name: str
    parameter_type: ParameterType
    low: float
    high: float
    log: bool = False

    def __post_init__(self) -> None:
        """Validate bounds and logarithmic-domain requirements."""
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("search parameter name must be non-empty")
        if not isinstance(self.parameter_type, ParameterType):
            raise ValueError("search parameter type is invalid")
        _finite_number(self.low, f"search_space.{self.name}.low")
        _finite_number(self.high, f"search_space.{self.name}.high")
        if self.high <= self.low:
            raise ValueError(f"search_space.{self.name}.high must exceed low")
        if not isinstance(self.log, bool):
            raise ValueError(f"search_space.{self.name}.log must be a boolean")
        if self.log and self.low <= 0:
            raise ValueError(
                f"search_space.{self.name}.low must be positive for log sampling"
            )
        if self.parameter_type is ParameterType.INTEGER:
            if not float(self.low).is_integer() or not float(self.high).is_integer():
                raise ValueError(
                    f"integer search_space.{self.name} bounds must be integers"
                )

    def contains(self, value: Any) -> bool:
        """Return whether ``value`` is a valid member of this dimension."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        numeric = float(value)
        if not isfinite(numeric) or not self.low <= numeric <= self.high:
            return False
        return self.parameter_type is ParameterType.FLOAT or numeric.is_integer()


@dataclass(frozen=True, slots=True)
class ObjectiveDefinition:
    """One physical metric and its optimizer-independent scalarization rule."""

    metric: str
    objective_type: ObjectiveType
    target: float | None = None
    weight: float = 1.0
    frequency_hz: float | None = None

    def __post_init__(self) -> None:
        """Validate objective semantics."""
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
            raise ValueError(
                f"objective '{self.metric}' only accepts target when type is target"
            )
        if self.frequency_hz is not None:
            _positive_number(
                self.frequency_hz, f"objectives.{self.metric}.frequency_hz"
            )


@dataclass(frozen=True, slots=True)
class ConstraintDefinition:
    """One physical metric inequality evaluated outside every optimizer."""

    metric: str
    operator: ConstraintOperator
    threshold: float
    frequency_hz: float | None = None

    def __post_init__(self) -> None:
        """Validate one constraint definition."""
        if not isinstance(self.metric, str) or not self.metric.strip():
            raise ValueError("constraint metric name must be non-empty")
        if not isinstance(self.operator, ConstraintOperator):
            raise ValueError("constraint operator is invalid")
        _finite_number(self.threshold, f"constraints.{self.metric}.threshold")
        if self.frequency_hz is not None:
            _positive_number(
                self.frequency_hz, f"constraints.{self.metric}.frequency_hz"
            )


@dataclass(frozen=True, slots=True)
class NgspiceConfig:
    """Common ngspice executable and AC-analysis settings."""

    executable: str = "ngspice"
    start_frequency_hz: float = 10.0
    stop_frequency_hz: float = 10_000_000.0
    points_per_decade: int = 50

    def __post_init__(self) -> None:
        """Validate executable and AC sweep."""
        if not isinstance(self.executable, str) or not self.executable.strip():
            raise ValueError("ngspice_config.executable must be non-empty")
        _positive_number(
            self.start_frequency_hz, "ngspice_config.start_frequency_hz"
        )
        _positive_number(
            self.stop_frequency_hz, "ngspice_config.stop_frequency_hz"
        )
        if self.stop_frequency_hz <= self.start_frequency_hz:
            raise ValueError(
                "ngspice_config.stop_frequency_hz must exceed start_frequency_hz"
            )
        if (
            isinstance(self.points_per_decade, bool)
            or not isinstance(self.points_per_decade, int)
            or self.points_per_decade < 2
        ):
            raise ValueError("ngspice_config.points_per_decade must be at least 2")


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
    optimizer_config: Mapping[str, Any] = field(default_factory=dict)
    ngspice_config: NgspiceConfig = NgspiceConfig()
    resume: bool = False
    timeout: float = 60.0

    def __post_init__(self) -> None:
        """Validate direct construction and research-baseline boundaries."""
        if not isinstance(self.experiment_name, str) or not self.experiment_name.strip():
            raise ValueError("experiment_name must be non-empty")
        if self.circuit_name != "rc_lowpass":
            raise ValueError("Research Task 1 supports only circuit_name='rc_lowpass'")
        if not isinstance(self.method, str) or not self.method.strip():
            raise ValueError("method must be non-empty")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        _positive_integer(self.simulation_budget, "simulation_budget")
        if not isinstance(self.output_dir, Path):
            raise ValueError("output_dir must be a pathlib.Path")
        if not self.search_space:
            raise ValueError("search_space must not be empty")
        if not all(isinstance(item, SearchParameter) for item in self.search_space):
            raise ValueError("search_space must contain SearchParameter objects")
        names = [parameter.name for parameter in self.search_space]
        if len(set(names)) != len(names):
            raise ValueError("search_space parameter names must be unique")
        if set(names) != {"resistance", "capacitance"}:
            raise ValueError(
                "rc_lowpass search_space must contain resistance and capacitance"
            )
        if not self.objectives:
            raise ValueError("objectives must not be empty")
        if not all(isinstance(item, ObjectiveDefinition) for item in self.objectives):
            raise ValueError("objectives must contain ObjectiveDefinition objects")
        objective_names = [objective.metric for objective in self.objectives]
        if len(set(objective_names)) != len(objective_names):
            raise ValueError("objective metric names must be unique")
        if not all(isinstance(item, ConstraintDefinition) for item in self.constraints):
            raise ValueError("constraints must contain ConstraintDefinition objects")
        constraint_names = [constraint.metric for constraint in self.constraints]
        if len(set(constraint_names)) != len(constraint_names):
            raise ValueError("constraint metric names must be unique")
        if not isinstance(self.optimizer_config, Mapping):
            raise ValueError("optimizer_config must be a mapping")
        forbidden_seed_keys = {
            "seed",
            "random_seed",
            "random_state",
            "sampler_seed",
        }
        duplicated = sorted(forbidden_seed_keys & set(self.optimizer_config))
        if duplicated:
            raise ValueError(
                "ExperimentConfig.seed is the only seed entry; remove optimizer_config "
                + ", ".join(duplicated)
            )
        try:
            json.dumps(dict(self.optimizer_config), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("optimizer_config must be JSON-compatible") from exc
        if not isinstance(self.ngspice_config, NgspiceConfig):
            raise ValueError("ngspice_config must be NgspiceConfig")
        if not isinstance(self.resume, bool):
            raise ValueError("resume must be a boolean")
        _positive_number(self.timeout, "timeout")

    @property
    def search_space_by_name(self) -> dict[str, SearchParameter]:
        """Return search dimensions keyed by canonical parameter name."""
        return {parameter.name: parameter for parameter in self.search_space}

    def validate_parameters(self, parameters: Mapping[str, Any]) -> None:
        """Require exactly one in-range value for every search dimension."""
        if not isinstance(parameters, Mapping):
            raise ValueError("candidate parameters must be a mapping")
        expected = set(self.search_space_by_name)
        actual = set(parameters)
        if actual != expected:
            missing = sorted(expected - actual)
            unknown = sorted(actual - expected)
            details: list[str] = []
            if missing:
                details.append(f"missing: {', '.join(missing)}")
            if unknown:
                details.append(f"unknown: {', '.join(unknown)}")
            raise ValueError("invalid candidate parameter keys (" + "; ".join(details) + ")")
        for name, definition in self.search_space_by_name.items():
            if not definition.contains(parameters[name]):
                raise ValueError(
                    f"candidate parameter '{name}' is outside its validated search space"
                )

    def to_dict(self) -> dict[str, Any]:
        """Return a stable YAML/JSON-compatible resolved configuration."""
        return {
            "experiment": {
                "name": self.experiment_name,
                "circuit": self.circuit_name,
                "method": self.method,
                "seed": self.seed,
                "simulation_budget": self.simulation_budget,
                "output_dir": self.output_dir.as_posix(),
                "resume": self.resume,
                "timeout": self.timeout,
            },
            "search_space": {
                parameter.name: {
                    "type": parameter.parameter_type.value,
                    "low": parameter.low,
                    "high": parameter.high,
                    "log": parameter.log,
                }
                for parameter in self.search_space
            },
            "objectives": {
                objective.metric: {
                    "type": objective.objective_type.value,
                    **(
                        {"target": objective.target}
                        if objective.target is not None
                        else {}
                    ),
                    "weight": objective.weight,
                    **(
                        {"frequency_hz": objective.frequency_hz}
                        if objective.frequency_hz is not None
                        else {}
                    ),
                }
                for objective in self.objectives
            },
            "constraints": {
                constraint.metric: {
                    "operator": constraint.operator.value,
                    "threshold": constraint.threshold,
                    **(
                        {"frequency_hz": constraint.frequency_hz}
                        if constraint.frequency_hz is not None
                        else {}
                    ),
                }
                for constraint in self.constraints
            },
            "optimizer_config": dict(self.optimizer_config),
            "ngspice_config": {
                "executable": self.ngspice_config.executable,
                "start_frequency_hz": self.ngspice_config.start_frequency_hz,
                "stop_frequency_hz": self.ngspice_config.stop_frequency_hz,
                "points_per_decade": self.ngspice_config.points_per_decade,
            },
        }

    def identity_sha256(self) -> str:
        """Hash experiment semantics while ignoring resume and output location."""
        payload = self.to_dict()
        payload["experiment"]["resume"] = False
        payload["experiment"]["output_dir"] = "<run-output>"
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return sha256(encoded).hexdigest()


def _parse_search_space(value: Any) -> tuple[SearchParameter, ...]:
    """Parse all search dimensions in declared YAML order."""
    mapping = _mapping(value, "search_space")
    parameters: list[SearchParameter] = []
    for name, raw_definition in mapping.items():
        definition = _mapping(raw_definition, f"search_space.{name}")
        _keys(
            definition,
            required={"type", "low", "high"},
            optional={"log"},
            context=f"search_space.{name}",
        )
        try:
            parameter_type = ParameterType(definition["type"])
        except (TypeError, ValueError):
            raise ConfigError(
                f"search_space.{name}.type must be 'float' or 'int'"
            ) from None
        try:
            parameters.append(
                SearchParameter(
                    name=name,
                    parameter_type=parameter_type,
                    low=_finite_number(definition["low"], f"search_space.{name}.low"),
                    high=_finite_number(
                        definition["high"], f"search_space.{name}.high"
                    ),
                    log=definition.get("log", False),
                )
            )
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
    return tuple(parameters)


def _parse_objectives(value: Any) -> tuple[ObjectiveDefinition, ...]:
    """Parse objective mappings without optimizer-specific behavior."""
    mapping = _mapping(value, "objectives")
    objectives: list[ObjectiveDefinition] = []
    for metric, raw_definition in mapping.items():
        definition = _mapping(raw_definition, f"objectives.{metric}")
        _keys(
            definition,
            required={"type"},
            optional={"target", "weight", "frequency_hz"},
            context=f"objectives.{metric}",
        )
        try:
            objective_type = ObjectiveType(definition["type"])
        except (TypeError, ValueError):
            raise ConfigError(
                f"objectives.{metric}.type must be maximize, minimize, or target"
            ) from None
        try:
            objectives.append(
                ObjectiveDefinition(
                    metric=metric,
                    objective_type=objective_type,
                    target=(
                        None
                        if "target" not in definition
                        else _finite_number(
                            definition["target"], f"objectives.{metric}.target"
                        )
                    ),
                    weight=_positive_number(
                        definition.get("weight", 1.0),
                        f"objectives.{metric}.weight",
                    ),
                    frequency_hz=(
                        None
                        if "frequency_hz" not in definition
                        else _positive_number(
                            definition["frequency_hz"],
                            f"objectives.{metric}.frequency_hz",
                        )
                    ),
                )
            )
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
    return tuple(objectives)


def _parse_constraints(value: Any) -> tuple[ConstraintDefinition, ...]:
    """Parse optional scalar constraints."""
    mapping = _mapping(value, "constraints")
    constraints: list[ConstraintDefinition] = []
    for metric, raw_definition in mapping.items():
        definition = _mapping(raw_definition, f"constraints.{metric}")
        _keys(
            definition,
            required={"operator", "threshold"},
            optional={"frequency_hz"},
            context=f"constraints.{metric}",
        )
        try:
            operator = ConstraintOperator(definition["operator"])
        except (TypeError, ValueError):
            raise ConfigError(
                f"constraints.{metric}.operator must be '>=' or '<='"
            ) from None
        try:
            constraints.append(
                ConstraintDefinition(
                    metric=metric,
                    operator=operator,
                    threshold=_finite_number(
                        definition["threshold"],
                        f"constraints.{metric}.threshold",
                    ),
                    frequency_hz=(
                        None
                        if "frequency_hz" not in definition
                        else _positive_number(
                            definition["frequency_hz"],
                            f"constraints.{metric}.frequency_hz",
                        )
                    ),
                )
            )
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
    return tuple(constraints)


def _parse_ngspice_config(value: Any) -> NgspiceConfig:
    """Parse common simulator and AC-analysis controls."""
    mapping = _mapping(value, "ngspice_config")
    _keys(
        mapping,
        required=set(),
        optional={
            "executable",
            "start_frequency_hz",
            "stop_frequency_hz",
            "points_per_decade",
        },
        context="ngspice_config",
    )
    try:
        return NgspiceConfig(
            executable=mapping.get("executable", "ngspice"),
            start_frequency_hz=_positive_number(
                mapping.get("start_frequency_hz", 10.0),
                "ngspice_config.start_frequency_hz",
            ),
            stop_frequency_hz=_positive_number(
                mapping.get("stop_frequency_hz", 10_000_000.0),
                "ngspice_config.stop_frequency_hz",
            ),
            points_per_decade=mapping.get("points_per_decade", 50),
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def experiment_config_from_mapping(value: Mapping[str, Any]) -> ExperimentConfig:
    """Validate and convert one already-loaded YAML mapping."""
    root = _mapping(value, "configuration root")
    _keys(
        root,
        required={"experiment", "search_space", "objectives"},
        optional={"constraints", "optimizer_config", "ngspice_config"},
        context="configuration root",
    )
    experiment = _mapping(root["experiment"], "experiment")
    _keys(
        experiment,
        required={"name", "circuit", "method", "seed", "simulation_budget"},
        optional={"output_dir", "resume", "timeout"},
        context="experiment",
    )
    optimizer_config = _mapping(root.get("optimizer_config", {}), "optimizer_config")
    try:
        return ExperimentConfig(
            experiment_name=experiment["name"],
            circuit_name=experiment["circuit"],
            method=experiment["method"],
            seed=experiment["seed"],
            simulation_budget=_positive_integer(
                experiment["simulation_budget"], "experiment.simulation_budget"
            ),
            output_dir=Path(experiment.get("output_dir", "research_runs")),
            search_space=_parse_search_space(root["search_space"]),
            objectives=_parse_objectives(root["objectives"]),
            constraints=_parse_constraints(root.get("constraints", {})),
            optimizer_config=dict(optimizer_config),
            ngspice_config=_parse_ngspice_config(root.get("ngspice_config", {})),
            resume=experiment.get("resume", False),
            timeout=_positive_number(
                experiment.get("timeout", 60.0), "experiment.timeout"
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(str(exc)) from exc


def load_experiment_config(config_path: str | Path) -> ExperimentConfig:
    """Read a UTF-8 YAML file into the common immutable experiment config."""
    source = Path(config_path).resolve()
    try:
        text = source.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"failed to read experiment config '{source}': {exc}") from exc
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in '{source}': {exc}") from exc
    return experiment_config_from_mapping(_mapping(loaded, "configuration root"))


def write_experiment_config(config: ExperimentConfig, path: str | Path) -> Path:
    """Write the fully resolved common configuration as deterministic YAML."""
    destination = Path(path).resolve()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            yaml.safe_dump(
                config.to_dict(),
                sort_keys=False,
                allow_unicode=True,
                default_flow_style=False,
            ),
            encoding="utf-8",
        )
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(
            f"failed to write resolved experiment config '{destination}': {exc}"
        ) from exc
    return destination
