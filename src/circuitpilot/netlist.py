"""Backward-compatible first-stage RC low-pass netlist API."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from circuitpilot.circuit_config import (
    ACAnalysisConfig,
    CircuitConfig,
    RCLowPassConfig,
)
from circuitpilot.netlist_generator import generate_netlist, write_netlist


@dataclass(frozen=True, slots=True)
class RCFilterConfig:
    """Electrical values and AC sweep settings for an RC low-pass filter."""

    resistance_ohm: float = 1_000.0
    capacitance_f: float = 159.154943e-9
    start_frequency_hz: float = 10.0
    stop_frequency_hz: float = 1_000_000.0
    points_per_decade: int = 100

    def __post_init__(self) -> None:
        """Validate values before they are interpolated into a netlist."""
        positive_values = {
            "resistance_ohm": self.resistance_ohm,
            "capacitance_f": self.capacitance_f,
            "start_frequency_hz": self.start_frequency_hz,
            "stop_frequency_hz": self.stop_frequency_hz,
        }
        for name, value in positive_values.items():
            if not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a finite positive number")
        if self.stop_frequency_hz <= self.start_frequency_hz:
            raise ValueError("stop_frequency_hz must be greater than start_frequency_hz")
        if self.points_per_decade < 2:
            raise ValueError("points_per_decade must be at least 2")


def generate_rc_lowpass_netlist(
    config: RCFilterConfig,
    output_path: str | Path,
) -> str:
    """Return an ngspice netlist for AC analysis of an RC low-pass filter.

    The generated control block writes three columns to ``output_path``:
    frequency in hertz, gain in decibels, and phase in degrees.

    Args:
        config: Component values and logarithmic sweep settings.
        output_path: Destination used by ngspice's ``wrdata`` command.

    Returns:
        Complete SPICE netlist text.

    Raises:
        NetlistError: If the destination contains a quote unsupported by the
            generated command.
    """
    generic_config = CircuitConfig(
        circuit=RCLowPassConfig(
            resistance_ohm=config.resistance_ohm,
            capacitance_f=config.capacitance_f,
        ),
        analysis=ACAnalysisConfig(
            start_frequency_hz=config.start_frequency_hz,
            stop_frequency_hz=config.stop_frequency_hz,
            points_per_decade=config.points_per_decade,
        ),
    )
    return generate_netlist(generic_config, output_path)


def write_rc_lowpass_netlist(
    netlist_path: str | Path,
    output_path: str | Path,
    config: RCFilterConfig | None = None,
) -> Path:
    """Generate and write an RC low-pass netlist as UTF-8 text.

    Parent directories for both the netlist and data output are created so a
    subsequent ngspice invocation can write its result.

    Args:
        netlist_path: File that will receive the generated SPICE source.
        output_path: Data file ngspice should create during AC analysis.
        config: Optional filter configuration. Defaults to ``RCFilterConfig``.

    Returns:
        Absolute path of the written netlist.

    Raises:
        NetlistError: If the file cannot be written.
    """
    legacy_config = config or RCFilterConfig()
    generic_config = CircuitConfig(
        circuit=RCLowPassConfig(
            resistance_ohm=legacy_config.resistance_ohm,
            capacitance_f=legacy_config.capacitance_f,
        ),
        analysis=ACAnalysisConfig(
            start_frequency_hz=legacy_config.start_frequency_hz,
            stop_frequency_hz=legacy_config.stop_frequency_hz,
            points_per_decade=legacy_config.points_per_decade,
        ),
    )
    return write_netlist(netlist_path, output_path, generic_config)
