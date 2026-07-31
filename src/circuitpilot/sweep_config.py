"""YAML configuration and deterministic combination generation for sweeps."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from itertools import product
from math import isfinite, pi
from pathlib import Path
from typing import Any, Mapping

import yaml

from circuitpilot.circuit_config import ACAnalysisConfig, CircuitType
from circuitpilot.exceptions import ConfigError


MAX_PARAMETER_VALUES = 100_000
MAX_COMBINATIONS = 100_000


@dataclass(frozen=True, slots=True)
class ParameterCombination:
    """One resistance/capacitance pair to simulate."""

    resistance_ohm: float
    capacitance_f: float


@dataclass(frozen=True, slots=True)
class SweepConfig:
    """Validated target, parameter space, and AC settings for a sweep."""

    target_cutoff_frequency_hz: float
    resistance_values_ohm: tuple[float, ...]
    capacitance_values_f: tuple[float, ...]
    analysis: ACAnalysisConfig
    circuit_type: CircuitType = CircuitType.RC_LOWPASS
    top_n: int = 10

    def __post_init__(self) -> None:
        """Validate programmatic construction as well as YAML-loaded values."""
        if self.circuit_type not in {
            CircuitType.RC_LOWPASS,
            CircuitType.RC_HIGHPASS,
        }:
            raise ValueError("cutoff sweeps support only rc_lowpass and rc_highpass")
        if not isinstance(self.analysis, ACAnalysisConfig):
            raise ValueError("analysis must be an ACAnalysisConfig")
        _require_positive_number(
            self.target_cutoff_frequency_hz, "target.cutoff_frequency"
        )
        if not self.resistance_values_ohm:
            raise ValueError("parameters.R must contain at least one value")
        if not self.capacitance_values_f:
            raise ValueError("parameters.C must contain at least one value")
        for value in self.resistance_values_ohm:
            _require_positive_number(value, "parameters.R")
        for value in self.capacitance_values_f:
            _require_positive_number(value, "parameters.C")
        if isinstance(self.top_n, bool) or not isinstance(self.top_n, int):
            raise ValueError("top_n must be an integer")
        if self.top_n <= 0:
            raise ValueError("top_n must be positive")
        if self.combination_count > MAX_COMBINATIONS:
            raise ValueError(
                f"parameter sweep exceeds the {MAX_COMBINATIONS} combination limit"
            )

    @property
    def combination_count(self) -> int:
        """Return the Cartesian-product size without materializing it."""
        return len(self.resistance_values_ohm) * len(self.capacitance_values_f)


def _require_positive_number(value: Any, context: str) -> float:
    """Convert a YAML number, including scientific-notation strings."""
    if isinstance(value, bool):
        raise ValueError(f"{context} must be a number")
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{context} must be a number") from None
    if not isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{context} must be a finite positive number")
    return parsed


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    """Return a string-keyed mapping or raise a configuration error."""
    if not isinstance(value, Mapping):
        raise ConfigError(f"{context} must be a YAML mapping")
    if not all(isinstance(key, str) for key in value):
        raise ConfigError(f"{context} keys must be strings")
    return value


def _check_keys(
    mapping: Mapping[str, Any],
    *,
    required: set[str],
    optional: set[str] | None = None,
    context: str,
) -> None:
    """Reject missing and unknown keys in one configuration section."""
    allowed = required | (optional or set())
    keys = set(mapping)
    missing = sorted(required - keys)
    unknown = sorted(keys - allowed)
    if missing:
        raise ConfigError(f"{context} is missing required field(s): {', '.join(missing)}")
    if unknown:
        raise ConfigError(f"{context} contains unknown field(s): {', '.join(unknown)}")


def _as_decimal(value: Any, context: str) -> Decimal:
    """Convert a positive number to Decimal for stable range expansion."""
    if isinstance(value, bool):
        raise ConfigError(f"{context} must be a number")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ConfigError(f"{context} must be a number") from None
    if not parsed.is_finite() or parsed <= 0:
        raise ConfigError(f"{context} must be a finite positive number")
    return parsed


def _parse_parameter_values(spec_value: Any, context: str) -> tuple[float, ...]:
    """Expand either ``values`` or inclusive ``min/max/step`` syntax."""
    spec = _require_mapping(spec_value, context)
    if set(spec) == {"values"}:
        raw_values = spec["values"]
        if not isinstance(raw_values, list) or not raw_values:
            raise ConfigError(f"{context}.values must be a non-empty YAML list")
        values = tuple(
            float(_as_decimal(value, f"{context}.values")) for value in raw_values
        )
        if len(set(values)) != len(values):
            raise ConfigError(f"{context}.values must not contain duplicates")
        return values

    _check_keys(
        spec,
        required={"min", "max", "step"},
        context=context,
    )
    minimum = _as_decimal(spec["min"], f"{context}.min")
    maximum = _as_decimal(spec["max"], f"{context}.max")
    step = _as_decimal(spec["step"], f"{context}.step")
    if maximum < minimum:
        raise ConfigError(f"{context}.max must be greater than or equal to min")
    count = int((maximum - minimum) // step) + 1
    if count > MAX_PARAMETER_VALUES:
        raise ConfigError(
            f"{context} expands beyond the {MAX_PARAMETER_VALUES} value limit"
        )
    return tuple(float(minimum + index * step) for index in range(count))


def _parse_circuit_type(value: Any) -> CircuitType:
    """Parse an optional circuit string or ``type`` mapping."""
    if value is None:
        return CircuitType.RC_LOWPASS
    if isinstance(value, Mapping):
        circuit = _require_mapping(value, "circuit")
        _check_keys(circuit, required={"type"}, context="circuit")
        value = circuit["type"]
    if not isinstance(value, str):
        raise ConfigError("circuit must be a type string or mapping")
    try:
        circuit_type = CircuitType(value)
    except ValueError:
        raise ConfigError(
            "sweep circuit must be either 'rc_lowpass' or 'rc_highpass'"
        ) from None
    if circuit_type is CircuitType.VOLTAGE_DIVIDER:
        raise ConfigError("voltage_divider has no cutoff frequency to optimize")
    return circuit_type


def _parse_target(value: Any) -> float:
    """Read the cutoff target, accepting the documented short key or Hz key."""
    target = _require_mapping(value, "target")
    keys = set(target)
    accepted = {"cutoff_frequency", "cutoff_frequency_hz"}
    if len(keys & accepted) != 1 or not keys <= accepted:
        raise ConfigError(
            "target must contain exactly one of cutoff_frequency or "
            "cutoff_frequency_hz"
        )
    key = next(iter(keys))
    try:
        return _require_positive_number(target[key], f"target.{key}")
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def _parse_analysis(
    value: Any,
    *,
    target_hz: float,
    resistance_values: tuple[float, ...],
    capacitance_values: tuple[float, ...],
) -> ACAnalysisConfig:
    """Read explicit analysis settings or derive a range covering all RC pairs."""
    if value is None:
        minimum_cutoff = 1.0 / (
            2.0 * pi * max(resistance_values) * max(capacitance_values)
        )
        maximum_cutoff = 1.0 / (
            2.0 * pi * min(resistance_values) * min(capacitance_values)
        )
        return ACAnalysisConfig(
            start_frequency_hz=min(target_hz, minimum_cutoff) / 10.0,
            stop_frequency_hz=max(target_hz, maximum_cutoff) * 10.0,
            points_per_decade=100,
        )

    analysis = _require_mapping(value, "analysis")
    _check_keys(
        analysis,
        required={"start_frequency_hz", "stop_frequency_hz", "points_per_decade"},
        context="analysis",
    )
    try:
        start = _require_positive_number(
            analysis["start_frequency_hz"], "analysis.start_frequency_hz"
        )
        stop = _require_positive_number(
            analysis["stop_frequency_hz"], "analysis.stop_frequency_hz"
        )
        points = analysis["points_per_decade"]
        if isinstance(points, bool) or not isinstance(points, int):
            raise ValueError("analysis.points_per_decade must be an integer")
        return ACAnalysisConfig(start, stop, points)
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def load_sweep_config(config_path: str | Path) -> SweepConfig:
    """Load and validate a parameter-sweep YAML file.

    Args:
        config_path: YAML file with ``target`` and ``parameters.R/C`` sections.

    Returns:
        Immutable sweep settings with all parameter values expanded.

    Raises:
        ConfigError: If the file, YAML syntax, or any sweep field is invalid.
    """
    source = Path(config_path).resolve()
    try:
        text = source.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"failed to read sweep configuration '{source}': {exc}") from exc
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in '{source}': {exc}") from exc

    root = _require_mapping(loaded, "sweep configuration root")
    _check_keys(
        root,
        required={"target", "parameters"},
        optional={"circuit", "analysis", "top_n"},
        context="sweep configuration root",
    )
    target_hz = _parse_target(root["target"])
    parameters = _require_mapping(root["parameters"], "parameters")
    _check_keys(parameters, required={"R", "C"}, context="parameters")
    resistance_values = _parse_parameter_values(parameters["R"], "parameters.R")
    capacitance_values = _parse_parameter_values(parameters["C"], "parameters.C")
    analysis = _parse_analysis(
        root.get("analysis"),
        target_hz=target_hz,
        resistance_values=resistance_values,
        capacitance_values=capacitance_values,
    )
    top_n = root.get("top_n", 10)
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise ConfigError("top_n must be a positive integer")
    try:
        return SweepConfig(
            target_cutoff_frequency_hz=target_hz,
            resistance_values_ohm=resistance_values,
            capacitance_values_f=capacitance_values,
            analysis=analysis,
            circuit_type=_parse_circuit_type(root.get("circuit")),
            top_n=top_n,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc


def generate_parameter_combinations(
    config: SweepConfig,
) -> tuple[ParameterCombination, ...]:
    """Return the deterministic Cartesian product of R and C values."""
    return tuple(
        ParameterCombination(resistance_ohm=resistance, capacitance_f=capacitance)
        for resistance, capacitance in product(
            config.resistance_values_ohm, config.capacitance_values_f
        )
    )
