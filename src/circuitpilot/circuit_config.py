"""Typed circuit configuration objects and safe YAML loading."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from pathlib import Path
from typing import Any, ClassVar, Mapping, TypeAlias

import yaml

from circuitpilot.exceptions import ConfigError


class CircuitType(str, Enum):
    """Circuit templates supported by CircuitPilot."""

    RC_LOWPASS = "rc_lowpass"
    RC_HIGHPASS = "rc_highpass"
    VOLTAGE_DIVIDER = "voltage_divider"


def _validate_positive_number(name: str, value: float) -> None:
    """Require a finite positive component or analysis value."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number")


@dataclass(frozen=True, slots=True)
class ACAnalysisConfig:
    """Logarithmic AC sweep settings shared by every circuit template."""

    start_frequency_hz: float = 10.0
    stop_frequency_hz: float = 1_000_000.0
    points_per_decade: int = 100

    def __post_init__(self) -> None:
        """Validate the AC sweep range and resolution."""
        _validate_positive_number("start_frequency_hz", self.start_frequency_hz)
        _validate_positive_number("stop_frequency_hz", self.stop_frequency_hz)
        if self.stop_frequency_hz <= self.start_frequency_hz:
            raise ValueError("stop_frequency_hz must be greater than start_frequency_hz")
        if isinstance(self.points_per_decade, bool) or not isinstance(
            self.points_per_decade, int
        ):
            raise ValueError("points_per_decade must be an integer")
        if self.points_per_decade < 2:
            raise ValueError("points_per_decade must be at least 2")


@dataclass(frozen=True, slots=True)
class RCLowPassConfig:
    """Component values for a first-order RC low-pass filter."""

    resistance_ohm: float
    capacitance_f: float
    circuit_type: ClassVar[CircuitType] = CircuitType.RC_LOWPASS

    def __post_init__(self) -> None:
        """Validate component values."""
        _validate_positive_number("resistance_ohm", self.resistance_ohm)
        _validate_positive_number("capacitance_f", self.capacitance_f)


@dataclass(frozen=True, slots=True)
class RCHighPassConfig:
    """Component values for a first-order RC high-pass filter."""

    resistance_ohm: float
    capacitance_f: float
    circuit_type: ClassVar[CircuitType] = CircuitType.RC_HIGHPASS

    def __post_init__(self) -> None:
        """Validate component values."""
        _validate_positive_number("resistance_ohm", self.resistance_ohm)
        _validate_positive_number("capacitance_f", self.capacitance_f)


@dataclass(frozen=True, slots=True)
class VoltageDividerConfig:
    """Resistor values for an unloaded two-resistor voltage divider."""

    resistance_top_ohm: float
    resistance_bottom_ohm: float
    circuit_type: ClassVar[CircuitType] = CircuitType.VOLTAGE_DIVIDER

    def __post_init__(self) -> None:
        """Validate both resistor values."""
        _validate_positive_number("resistance_top_ohm", self.resistance_top_ohm)
        _validate_positive_number("resistance_bottom_ohm", self.resistance_bottom_ohm)


CircuitParameters: TypeAlias = (
    RCLowPassConfig | RCHighPassConfig | VoltageDividerConfig
)


@dataclass(frozen=True, slots=True)
class CircuitConfig:
    """Complete Python representation of one circuit simulation."""

    circuit: CircuitParameters
    analysis: ACAnalysisConfig

    def __post_init__(self) -> None:
        """Ensure programmatic callers also provide supported config objects."""
        if not isinstance(
            self.circuit, (RCLowPassConfig, RCHighPassConfig, VoltageDividerConfig)
        ):
            raise ValueError("circuit must be a supported circuit configuration")
        if not isinstance(self.analysis, ACAnalysisConfig):
            raise ValueError("analysis must be an ACAnalysisConfig")

    @property
    def circuit_type(self) -> CircuitType:
        """Return the selected circuit template identifier."""
        return self.circuit.circuit_type


def _require_mapping(value: Any, context: str) -> Mapping[str, Any]:
    """Return ``value`` as a string-keyed mapping or raise ``ConfigError``."""
    if not isinstance(value, Mapping):
        raise ConfigError(f"{context} must be a YAML mapping")
    if not all(isinstance(key, str) for key in value):
        raise ConfigError(f"{context} keys must be strings")
    return value


def _require_exact_keys(
    mapping: Mapping[str, Any], required: set[str], context: str
) -> None:
    """Reject missing and misspelled configuration fields."""
    keys = set(mapping)
    missing = sorted(required - keys)
    unknown = sorted(keys - required)
    if missing:
        raise ConfigError(f"{context} is missing required field(s): {', '.join(missing)}")
    if unknown:
        raise ConfigError(f"{context} contains unknown field(s): {', '.join(unknown)}")


def _build_circuit(circuit_data: Mapping[str, Any]) -> CircuitParameters:
    """Validate and convert the YAML circuit section."""
    _require_exact_keys(circuit_data, {"type", "parameters"}, "circuit")
    raw_type = circuit_data["type"]
    if not isinstance(raw_type, str):
        raise ConfigError("circuit.type must be a string")
    try:
        circuit_type = CircuitType(raw_type)
    except ValueError:
        supported = ", ".join(member.value for member in CircuitType)
        raise ConfigError(
            f"unsupported circuit.type '{raw_type}'; expected one of: {supported}"
        ) from None

    parameters = _require_mapping(circuit_data["parameters"], "circuit.parameters")
    if circuit_type in {CircuitType.RC_LOWPASS, CircuitType.RC_HIGHPASS}:
        required = {"resistance_ohm", "capacitance_f"}
        _require_exact_keys(parameters, required, "circuit.parameters")
        config_class = (
            RCLowPassConfig
            if circuit_type is CircuitType.RC_LOWPASS
            else RCHighPassConfig
        )
        return config_class(
            resistance_ohm=parameters["resistance_ohm"],
            capacitance_f=parameters["capacitance_f"],
        )

    required = {"resistance_top_ohm", "resistance_bottom_ohm"}
    _require_exact_keys(parameters, required, "circuit.parameters")
    return VoltageDividerConfig(
        resistance_top_ohm=parameters["resistance_top_ohm"],
        resistance_bottom_ohm=parameters["resistance_bottom_ohm"],
    )


def _build_analysis(analysis_data: Mapping[str, Any]) -> ACAnalysisConfig:
    """Validate and convert the YAML analysis section."""
    required = {"start_frequency_hz", "stop_frequency_hz", "points_per_decade"}
    _require_exact_keys(analysis_data, required, "analysis")
    return ACAnalysisConfig(
        start_frequency_hz=analysis_data["start_frequency_hz"],
        stop_frequency_hz=analysis_data["stop_frequency_hz"],
        points_per_decade=analysis_data["points_per_decade"],
    )


def load_circuit_config(config_path: str | Path) -> CircuitConfig:
    """Read, validate, and convert a YAML simulation configuration.

    Args:
        config_path: YAML file containing ``circuit`` and ``analysis`` sections.

    Returns:
        Fully validated, immutable Python configuration objects.

    Raises:
        ConfigError: If the file cannot be read, YAML is unsafe/malformed, or
            any required value is missing or invalid.
    """
    source = Path(config_path).resolve()
    try:
        text = source.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"failed to read configuration '{source}': {exc}") from exc

    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in '{source}': {exc}") from exc

    root = _require_mapping(loaded, "configuration root")
    _require_exact_keys(root, {"circuit", "analysis"}, "configuration root")
    try:
        circuit = _build_circuit(_require_mapping(root["circuit"], "circuit"))
        analysis = _build_analysis(_require_mapping(root["analysis"], "analysis"))
    except ValueError as exc:
        raise ConfigError(str(exc)) from exc
    return CircuitConfig(circuit=circuit, analysis=analysis)
