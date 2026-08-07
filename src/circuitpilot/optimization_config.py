"""Typed YAML configuration for simulation-driven circuit optimization."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite, log10, pi
from pathlib import Path
from typing import Any, Mapping

import yaml

from circuitpilot.circuit_config import ACAnalysisConfig, CircuitType
from circuitpilot.exceptions import ConfigError


class ObjectiveGoal(str, Enum):
    """Directions supported by the simulation objective."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"
    TARGET = "target"


class ObjectiveMetric(str, Enum):
    """AC metrics supported by the optimizer; power means derived RC power."""

    GAIN = "gain"
    POWER = "power"
    BANDWIDTH = "bandwidth"


class ParameterScale(str, Enum):
    """Coordinate scale used to search one component value."""

    LINEAR = "linear"
    LOG = "log"


def _positive_number(value: Any, context: str) -> float:
    """Convert YAML numeric syntax and require a finite positive value."""
    if isinstance(value, bool):
        raise ValueError(f"{context} must be a number")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{context} must be a number") from None
    if not isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{context} must be a finite positive number")
    return parsed


@dataclass(frozen=True, slots=True)
class ParameterBounds:
    """Validated lower/upper bounds and optimizer coordinate scale."""

    minimum: float
    maximum: float
    scale: ParameterScale = ParameterScale.LOG

    def __post_init__(self) -> None:
        """Validate bounds for direct programmatic construction."""
        _positive_number(self.minimum, "parameter minimum")
        _positive_number(self.maximum, "parameter maximum")
        if self.maximum <= self.minimum:
            raise ValueError("parameter maximum must be greater than minimum")
        if not isinstance(self.scale, ParameterScale):
            raise ValueError("parameter scale must be 'linear' or 'log'")

    @property
    def optimizer_bounds(self) -> tuple[float, float]:
        """Return bounds in the coordinate system passed to SciPy."""
        if self.scale is ParameterScale.LOG:
            return log10(self.minimum), log10(self.maximum)
        return self.minimum, self.maximum

    def decode(self, coordinate: float) -> float:
        """Convert one optimizer coordinate to a physical component value."""
        return 10.0**coordinate if self.scale is ParameterScale.LOG else coordinate


@dataclass(frozen=True, slots=True)
class ObjectiveConfig:
    """One supported performance metric and its optimization direction."""

    metric: ObjectiveMetric
    goal: ObjectiveGoal
    target_value: float | None = None
    evaluation_frequency_hz: float | None = None

    def __post_init__(self) -> None:
        """Reject unsupported or physically ambiguous objective combinations."""
        if not isinstance(self.metric, ObjectiveMetric):
            raise ValueError("objective metric is invalid")
        if not isinstance(self.goal, ObjectiveGoal):
            raise ValueError("objective goal is invalid")
        supported = {
            ObjectiveMetric.GAIN: ObjectiveGoal.MAXIMIZE,
            ObjectiveMetric.POWER: ObjectiveGoal.MINIMIZE,
            ObjectiveMetric.BANDWIDTH: ObjectiveGoal.TARGET,
        }
        expected_goal = supported[self.metric]
        if self.goal is not expected_goal:
            raise ValueError(
                f"objective '{self.metric.value}' requires goal "
                f"'{expected_goal.value}'"
            )
        if self.metric is ObjectiveMetric.BANDWIDTH:
            if self.target_value is None:
                raise ValueError("bandwidth target requires objective.target_value")
            _positive_number(self.target_value, "objective.target_value")
            if self.evaluation_frequency_hz is not None:
                raise ValueError(
                    "bandwidth does not use objective.evaluation_frequency_hz"
                )
        else:
            if self.target_value is not None:
                raise ValueError("gain and power objectives do not use target_value")
            if self.evaluation_frequency_hz is None:
                raise ValueError(
                    f"{self.metric.value} requires "
                    "objective.evaluation_frequency_hz"
                )
            _positive_number(
                self.evaluation_frequency_hz,
                "objective.evaluation_frequency_hz",
            )


@dataclass(frozen=True, slots=True)
class OptimizerSettings:
    """Controls for SciPy differential evolution."""

    max_iterations: int = 10
    population_size: int = 8
    tolerance: float = 1e-3
    seed: int = 42
    polish: bool = True

    def __post_init__(self) -> None:
        """Validate optimizer limits and deterministic seed."""
        if isinstance(self.max_iterations, bool) or not isinstance(
            self.max_iterations, int
        ):
            raise ValueError("optimizer.max_iterations must be an integer")
        if self.max_iterations <= 0:
            raise ValueError("optimizer.max_iterations must be positive")
        if isinstance(self.population_size, bool) or not isinstance(
            self.population_size, int
        ):
            raise ValueError("optimizer.population_size must be an integer")
        if self.population_size < 2:
            raise ValueError("optimizer.population_size must be at least 2")
        if (
            isinstance(self.tolerance, bool)
            or not isinstance(self.tolerance, (int, float))
            or not isfinite(float(self.tolerance))
            or self.tolerance < 0
        ):
            raise ValueError("optimizer.tolerance must be finite and non-negative")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int):
            raise ValueError("optimizer.seed must be an integer")
        if not isinstance(self.polish, bool):
            raise ValueError("optimizer.polish must be a boolean")


@dataclass(frozen=True, slots=True)
class OptimizationConfig:
    """Complete parameter space, objective, AC analysis, and solver controls."""

    circuit_type: CircuitType
    resistance: ParameterBounds
    capacitance: ParameterBounds
    objective: ObjectiveConfig
    analysis: ACAnalysisConfig
    optimizer: OptimizerSettings = OptimizerSettings()

    def __post_init__(self) -> None:
        """Validate direct construction and supported circuit templates."""
        if self.circuit_type not in {
            CircuitType.RC_LOWPASS,
            CircuitType.RC_HIGHPASS,
        }:
            raise ValueError("optimization supports only rc_lowpass and rc_highpass")
        if not isinstance(self.resistance, ParameterBounds):
            raise ValueError("resistance must be ParameterBounds")
        if not isinstance(self.capacitance, ParameterBounds):
            raise ValueError("capacitance must be ParameterBounds")
        if not isinstance(self.objective, ObjectiveConfig):
            raise ValueError("objective must be ObjectiveConfig")
        if not isinstance(self.analysis, ACAnalysisConfig):
            raise ValueError("analysis must be ACAnalysisConfig")
        if not isinstance(self.optimizer, OptimizerSettings):
            raise ValueError("optimizer must be OptimizerSettings")

    def decode_parameters(self, coordinates: tuple[float, float]) -> tuple[float, float]:
        """Decode SciPy coordinates to ``(resistance_ohm, capacitance_f)``."""
        if len(coordinates) != 2:
            raise ValueError("optimizer coordinates must contain R and C")
        return (
            self.resistance.decode(float(coordinates[0])),
            self.capacitance.decode(float(coordinates[1])),
        )


def _mapping(value: Any, context: str) -> Mapping[str, Any]:
    """Require a string-keyed YAML mapping."""
    if not isinstance(value, Mapping):
        raise ConfigError(f"{context} must be a YAML mapping")
    if not all(isinstance(key, str) for key in value):
        raise ConfigError(f"{context} keys must be strings")
    return value


def _check_keys(
    value: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
    context: str,
) -> None:
    """Reject missing and misspelled configuration keys."""
    allowed = required | (optional or set())
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - allowed)
    if missing:
        raise ConfigError(f"{context} is missing required field(s): {', '.join(missing)}")
    if unknown:
        raise ConfigError(f"{context} contains unknown field(s): {', '.join(unknown)}")


def _parse_circuit(value: Any) -> CircuitType:
    """Read ``circuit.type`` and limit optimization to RC filters."""
    circuit = _mapping(value, "circuit")
    _check_keys(circuit, required={"type"}, context="circuit")
    raw_type = circuit["type"]
    if not isinstance(raw_type, str):
        raise ConfigError("circuit.type must be a string")
    try:
        circuit_type = CircuitType(raw_type)
    except ValueError:
        raise ConfigError("circuit.type must be 'rc_lowpass' or 'rc_highpass'") from None
    if circuit_type is CircuitType.VOLTAGE_DIVIDER:
        raise ConfigError("voltage_divider is not supported by the R/C optimizer")
    return circuit_type


def _parse_bounds(value: Any, context: str) -> ParameterBounds:
    """Read one component's continuous range and optional coordinate scale."""
    bounds = _mapping(value, context)
    _check_keys(
        bounds,
        required={"min", "max"},
        optional={"scale"},
        context=context,
    )
    raw_scale = bounds.get("scale", ParameterScale.LOG.value)
    try:
        scale = ParameterScale(raw_scale)
    except (TypeError, ValueError):
        raise ConfigError(f"{context}.scale must be 'linear' or 'log'") from None
    try:
        return ParameterBounds(
            minimum=_positive_number(bounds["min"], f"{context}.min"),
            maximum=_positive_number(bounds["max"], f"{context}.max"),
            scale=scale,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def _parse_objective(value: Any) -> ObjectiveConfig:
    """Read and validate the documented objective mapping."""
    objective = _mapping(value, "objective")
    _check_keys(
        objective,
        required={"metric", "goal"},
        optional={"target_value", "evaluation_frequency_hz"},
        context="objective",
    )
    try:
        metric = ObjectiveMetric(objective["metric"])
    except (TypeError, ValueError):
        choices = ", ".join(metric.value for metric in ObjectiveMetric)
        raise ConfigError(f"objective.metric must be one of: {choices}") from None
    try:
        goal = ObjectiveGoal(objective["goal"])
    except (TypeError, ValueError):
        choices = ", ".join(goal.value for goal in ObjectiveGoal)
        raise ConfigError(f"objective.goal must be one of: {choices}") from None
    target = objective.get("target_value")
    evaluation_frequency = objective.get("evaluation_frequency_hz")
    try:
        return ObjectiveConfig(
            metric=metric,
            goal=goal,
            target_value=(
                None
                if target is None
                else _positive_number(target, "objective.target_value")
            ),
            evaluation_frequency_hz=(
                None
                if evaluation_frequency is None
                else _positive_number(
                    evaluation_frequency,
                    "objective.evaluation_frequency_hz",
                )
            ),
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def _parse_optimizer(value: Any) -> OptimizerSettings:
    """Read optional differential-evolution settings."""
    if value is None:
        return OptimizerSettings()
    settings = _mapping(value, "optimizer")
    _check_keys(
        settings,
        required=set(),
        optional={
            "max_iterations",
            "population_size",
            "tolerance",
            "seed",
            "polish",
        },
        context="optimizer",
    )
    try:
        return OptimizerSettings(
            max_iterations=settings.get("max_iterations", 10),
            population_size=settings.get("population_size", 8),
            tolerance=settings.get("tolerance", 1e-3),
            seed=settings.get("seed", 42),
            polish=settings.get("polish", True),
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def _parse_analysis(
    value: Any,
    *,
    resistance: ParameterBounds,
    capacitance: ParameterBounds,
    objective: ObjectiveConfig,
) -> ACAnalysisConfig:
    """Read explicit AC settings or derive coverage from R/C extremes."""
    if value is None:
        minimum_cutoff = 1.0 / (
            2.0 * pi * resistance.maximum * capacitance.maximum
        )
        maximum_cutoff = 1.0 / (
            2.0 * pi * resistance.minimum * capacitance.minimum
        )
        reference = (
            objective.target_value
            if objective.metric is ObjectiveMetric.BANDWIDTH
            else objective.evaluation_frequency_hz
        )
        assert reference is not None
        return ACAnalysisConfig(
            start_frequency_hz=min(minimum_cutoff, reference) / 10.0,
            stop_frequency_hz=max(maximum_cutoff, reference) * 10.0,
            points_per_decade=100,
        )
    analysis = _mapping(value, "analysis")
    _check_keys(
        analysis,
        required={"start_frequency_hz", "stop_frequency_hz", "points_per_decade"},
        context="analysis",
    )
    try:
        points = analysis["points_per_decade"]
        if isinstance(points, bool) or not isinstance(points, int):
            raise ValueError("analysis.points_per_decade must be an integer")
        return ACAnalysisConfig(
            start_frequency_hz=_positive_number(
                analysis["start_frequency_hz"], "analysis.start_frequency_hz"
            ),
            stop_frequency_hz=_positive_number(
                analysis["stop_frequency_hz"], "analysis.stop_frequency_hz"
            ),
            points_per_decade=points,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def load_optimization_config(config_path: str | Path) -> OptimizationConfig:
    """Load and validate one simulation-driven optimization YAML file.

    Args:
        config_path: YAML file defining an RC template, objective, R/C bounds,
            and optional optimizer and AC-analysis controls.

    Returns:
        Immutable settings ready for ``run_circuit_optimization``.

    Raises:
        ConfigError: If the file, YAML, or any semantic constraint is invalid.
    """
    source = Path(config_path).resolve()
    try:
        text = source.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise ConfigError(
            f"failed to read optimization configuration '{source}': {exc}"
        ) from exc
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in '{source}': {exc}") from exc

    root = _mapping(loaded, "optimization configuration root")
    _check_keys(
        root,
        required={"circuit", "objective", "parameters"},
        optional={"optimizer", "analysis"},
        context="optimization configuration root",
    )
    parameters = _mapping(root["parameters"], "parameters")
    _check_keys(parameters, required={"R", "C"}, context="parameters")
    resistance = _parse_bounds(parameters["R"], "parameters.R")
    capacitance = _parse_bounds(parameters["C"], "parameters.C")
    objective = _parse_objective(root["objective"])
    analysis = _parse_analysis(
        root.get("analysis"),
        resistance=resistance,
        capacitance=capacitance,
        objective=objective,
    )
    try:
        return OptimizationConfig(
            circuit_type=_parse_circuit(root["circuit"]),
            resistance=resistance,
            capacitance=capacitance,
            objective=objective,
            analysis=analysis,
            optimizer=_parse_optimizer(root.get("optimizer")),
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
