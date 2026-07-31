"""Dynamic SPICE netlist generation for supported circuit templates."""

from __future__ import annotations

import os
from pathlib import Path

from circuitpilot.circuit_config import (
    CircuitConfig,
    RCHighPassConfig,
    RCLowPassConfig,
    VoltageDividerConfig,
)
from circuitpilot.exceptions import NetlistError


def _format_output_path(output_path: str | Path) -> str:
    """Return an ngspice-friendly unquoted data path."""
    data_path = Path(output_path).as_posix()
    if '"' in data_path:
        raise NetlistError("output_path must not contain a double quote")
    if any(character.isspace() for character in data_path):
        raise NetlistError(
            "ngspice wrdata paths must not contain whitespace; use write_netlist "
            "to generate a relative path"
        )
    return data_path


def _circuit_lines(config: CircuitConfig) -> tuple[str, ...]:
    """Render component statements for the configured circuit template."""
    circuit = config.circuit
    if isinstance(circuit, RCLowPassConfig):
        return (
            "* CircuitPilot RC low-pass filter",
            "Vin in 0 AC 1",
            f"R1 in out {circuit.resistance_ohm:.12g}",
            f"C1 out 0 {circuit.capacitance_f:.12g}",
        )
    if isinstance(circuit, RCHighPassConfig):
        return (
            "* CircuitPilot RC high-pass filter",
            "Vin in 0 AC 1",
            f"C1 in out {circuit.capacitance_f:.12g}",
            f"R1 out 0 {circuit.resistance_ohm:.12g}",
        )
    if isinstance(circuit, VoltageDividerConfig):
        return (
            "* CircuitPilot voltage divider",
            "Vin in 0 AC 1",
            f"R1 in out {circuit.resistance_top_ohm:.12g}",
            f"R2 out 0 {circuit.resistance_bottom_ohm:.12g}",
        )
    raise NetlistError(f"unsupported circuit configuration: {type(circuit).__name__}")


def generate_netlist(config: CircuitConfig, output_path: str | Path) -> str:
    """Generate a complete ngspice AC netlist from a typed configuration.

    Args:
        config: Circuit template, component values, and AC sweep settings.
        output_path: Destination for frequency, gain, and phase data.

    Returns:
        Complete SPICE netlist text ready for batch execution.
    """
    analysis = config.analysis
    lines = [*_circuit_lines(config), ".control", "set wr_singlescale", "set wr_vecnames"]
    lines.append(
        f"ac dec {analysis.points_per_decade} "
        f"{analysis.start_frequency_hz:.12g} {analysis.stop_frequency_hz:.12g}"
    )
    lines.extend(
        (
            f"wrdata {_format_output_path(output_path)} vdb(out) vp(out)",
            "quit",
            ".endc",
            ".end",
        )
    )
    return "\n".join(lines) + "\n"


def write_netlist(
    netlist_path: str | Path,
    output_path: str | Path,
    config: CircuitConfig,
) -> Path:
    """Generate and write a configured SPICE netlist as UTF-8 text.

    Args:
        netlist_path: File that will receive the SPICE source.
        output_path: Data file ngspice should create during AC analysis.
        config: Validated circuit simulation configuration.

    Returns:
        Absolute path of the written netlist.

    Raises:
        NetlistError: If required directories or the file cannot be written.
    """
    destination = Path(netlist_path).resolve()
    data_destination = Path(output_path).resolve()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        data_destination.parent.mkdir(parents=True, exist_ok=True)
        relative_data_path = os.path.relpath(data_destination, destination.parent)
        destination.write_text(
            generate_netlist(config, relative_data_path),
            encoding="utf-8",
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise NetlistError(f"failed to write netlist '{destination}': {exc}") from exc
    return destination
