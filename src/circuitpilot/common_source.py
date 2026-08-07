"""Transistor-level common-source benchmark netlists and measurements."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import os
from pathlib import Path
import re
from typing import Any, Mapping

from circuitpilot.analysis import find_cutoff_frequency
from circuitpilot.exceptions import AnalysisError, ConfigError, NetlistError, ParseError
from circuitpilot.mosfet_model import MosfetModelConfig, mosfet_model_from_mapping
from circuitpilot.parser import ACAnalysisResult
from circuitpilot.power_metrics import dc_supply_power


COMMON_SOURCE_PARAMETER_NAMES = {
    "width_m",
    "length_m",
    "drain_resistance_ohm",
    "input_bias_v",
}


@dataclass(frozen=True, slots=True)
class CommonSourceCircuitConfig:
    """Fixed benchmark values that are never hidden in Python defaults."""

    supply_voltage_v: float
    load_capacitance_f: float
    temperature_c: float
    model: MosfetModelConfig

    def __post_init__(self) -> None:
        for name, value in (
            ("supply_voltage_v", self.supply_voltage_v),
            ("load_capacitance_f", self.load_capacitance_f),
            ("temperature_c", self.temperature_c),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"circuit_config.{name} must be numeric")
            if not isfinite(float(value)):
                raise ValueError(f"circuit_config.{name} must be finite")
        if self.supply_voltage_v <= 0:
            raise ValueError("circuit_config.supply_voltage_v must be positive")
        if self.load_capacitance_f <= 0:
            raise ValueError("circuit_config.load_capacitance_f must be positive")
        if not isinstance(self.model, MosfetModelConfig):
            raise ValueError("circuit_config.mosfet_model must be MosfetModelConfig")

    def to_dict(self) -> dict[str, Any]:
        """Return all fixed topology/model values for YAML and hashing."""
        return {
            "supply_voltage_v": self.supply_voltage_v,
            "load_capacitance_f": self.load_capacitance_f,
            "temperature_c": self.temperature_c,
            "mosfet_model": self.model.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class OperatingPointResult:
    """Required and optional values parsed from a real ngspice `.op` run."""

    supply_voltage_v: float
    input_voltage_v: float
    output_voltage_v: float
    supply_current_a: float
    device_quantities: Mapping[str, float]
    unsupported_device_quantities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CommonSourceMetrics:
    """Physical benchmark metrics derived exclusively from ngspice output."""

    low_frequency_gain_db: float
    peak_gain_db: float
    bandwidth_3db_hz: float
    dc_power_w: float
    output_dc_voltage: float
    supply_current_a: float

    def to_dict(self) -> dict[str, float]:
        """Return canonical research metric names."""
        return {
            "gain_db": self.low_frequency_gain_db,
            "low_frequency_gain_db": self.low_frequency_gain_db,
            "peak_gain_db": self.peak_gain_db,
            "bandwidth_hz": self.bandwidth_3db_hz,
            "bandwidth_3db_hz": self.bandwidth_3db_hz,
            "dc_power_w": self.dc_power_w,
            "dc_supply_power": self.dc_power_w,
            "output_dc_voltage": self.output_dc_voltage,
            "supply_current_a": self.supply_current_a,
        }


def common_source_config_from_mapping(
    value: Mapping[str, Any], *, base_directory: Path | None = None
) -> CommonSourceCircuitConfig:
    """Parse fixed common-source values from a strict YAML mapping."""
    if not isinstance(value, Mapping):
        raise ConfigError("circuit_config must be a YAML mapping")
    required = {
        "supply_voltage_v",
        "load_capacitance_f",
        "temperature_c",
        "mosfet_model",
    }
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    if missing:
        raise ConfigError(f"circuit_config is missing required field(s): {', '.join(missing)}")
    if unknown:
        raise ConfigError(f"circuit_config contains unknown field(s): {', '.join(unknown)}")
    try:
        return CommonSourceCircuitConfig(
            supply_voltage_v=float(value["supply_voltage_v"]),
            load_capacitance_f=float(value["load_capacitance_f"]),
            temperature_c=float(value["temperature_c"]),
            model=mosfet_model_from_mapping(
                value["mosfet_model"], base_directory=base_directory
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(str(exc)) from exc


def _relative_output_path(output_path: Path, netlist_directory: Path) -> str:
    value = Path(os.path.relpath(output_path.resolve(), netlist_directory.resolve())).as_posix()
    if '"' in value or any(character.isspace() for character in value):
        raise NetlistError("ngspice output paths must not contain whitespace or quotes")
    return value


def generate_common_source_netlist(
    config: CommonSourceCircuitConfig,
    parameters: Mapping[str, float | int],
    *,
    ac_output_path: str,
    op_output_path: str,
    device_op_output_path: str,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
) -> str:
    """Generate one combined `.op` + `.ac` common-source ngspice netlist."""
    if set(parameters) != COMMON_SOURCE_PARAMETER_NAMES:
        raise NetlistError("common-source parameters must be width_m, length_m, drain_resistance_ohm, and input_bias_v")
    width = float(parameters["width_m"])
    length = float(parameters["length_m"])
    resistance = float(parameters["drain_resistance_ohm"])
    bias = float(parameters["input_bias_v"])
    values = (width, length, resistance, bias, start_frequency_hz, stop_frequency_hz)
    if not all(isfinite(value) for value in values):
        raise NetlistError("common-source netlist values must be finite")
    if width <= 0 or length <= 0 or resistance <= 0:
        raise NetlistError("common-source W, L, and RD must be positive")
    if not 0 <= bias <= config.supply_voltage_v:
        raise NetlistError("common-source input_bias_v must be between ground and VDD")
    if start_frequency_hz <= 0 or stop_frequency_hz <= start_frequency_hz:
        raise NetlistError("invalid common-source AC frequency range")
    if points_per_decade < 2:
        raise NetlistError("points_per_decade must be at least 2")
    model_path = config.model.require_library().as_posix()
    if '"' in model_path:
        raise NetlistError("MOSFET model path must not contain a double quote")
    include = (
        f'.lib "{model_path}" {config.model.model_section}'
        if config.model.model_section
        else f'.include "{model_path}"'
    )
    device = (
        f"M1 out in 0 0 {config.model.model_name} W={width:.12g} L={length:.12g}"
        if config.model.device_kind == "mosfet"
        else f"X1 out in 0 0 {config.model.model_name} W={width:.12g} L={length:.12g}"
    )
    optional_vectors = (
        "@m1[vgs] @m1[vds] @m1[gm] @m1[gds] @m1[vth] @m1[vdsat]"
        if config.model.device_kind == "mosfet"
        else ""
    )
    lines = [
        "* CircuitPilot transistor-level common-source amplifier",
        include,
        f".temp {config.temperature_c:.12g}",
        f"VDD vdd 0 DC {config.supply_voltage_v:.12g}",
        f"VIN in 0 DC {bias:.12g} AC 1",
        f"RD vdd out {resistance:.12g}",
        device,
        f"CL out 0 {config.load_capacitance_f:.12g}",
        ".control",
        "set wr_singlescale",
        "set wr_vecnames",
        "op",
        f"wrdata {op_output_path} v(vdd) v(in) v(out) i(vdd)",
    ]
    if optional_vectors:
        lines.append(f"wrdata {device_op_output_path} {optional_vectors}")
    lines.extend(
        (
            f"ac dec {points_per_decade} {start_frequency_hz:.12g} {stop_frequency_hz:.12g}",
            f"wrdata {ac_output_path} vdb(out) vp(out)",
            "quit",
            ".endc",
            ".end",
        )
    )
    return "\n".join(lines) + "\n"


def write_common_source_netlist(
    netlist_path: str | Path,
    config: CommonSourceCircuitConfig,
    parameters: Mapping[str, float | int],
    *,
    ac_output_path: str | Path,
    op_output_path: str | Path,
    device_op_output_path: str | Path,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
) -> Path:
    """Write a common-source netlist with paths relative to the netlist."""
    destination = Path(netlist_path).resolve()
    outputs = tuple(Path(path).resolve() for path in (ac_output_path, op_output_path, device_op_output_path))
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        for output in outputs:
            output.parent.mkdir(parents=True, exist_ok=True)
        text = generate_common_source_netlist(
            config,
            parameters,
            ac_output_path=_relative_output_path(outputs[0], destination.parent),
            op_output_path=_relative_output_path(outputs[1], destination.parent),
            device_op_output_path=_relative_output_path(outputs[2], destination.parent),
            start_frequency_hz=start_frequency_hz,
            stop_frequency_hz=stop_frequency_hz,
            points_per_decade=points_per_decade,
        )
        destination.write_text(text, encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise NetlistError(f"failed to write common-source netlist '{destination}': {exc}") from exc
    return destination


_SEPARATOR = re.compile(r"[\s,]+")


def _read_numeric_rows(path: Path) -> list[list[float]]:
    try:
        lines = path.resolve().read_text(encoding="utf-8", errors="strict").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ParseError(f"failed to read operating-point output '{path.resolve()}': {exc}") from exc
    rows: list[list[float]] = []
    for line_number, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", "*")):
            continue
        tokens = [token for token in _SEPARATOR.split(stripped) if token]
        try:
            values = [float(token.replace("D", "E").replace("d", "e")) for token in tokens]
        except ValueError:
            if not rows:
                continue
            raise ParseError(f"invalid operating-point data at line {line_number}: {raw!r}") from None
        if not all(isfinite(value) for value in values):
            raise ParseError(f"non-finite operating-point value at line {line_number}")
        rows.append(values)
    if not rows:
        raise ParseError(f"operating-point output contains no numeric row: '{path.resolve()}'")
    return rows


def parse_operating_point(
    op_output_path: str | Path,
    device_op_output_path: str | Path | None = None,
) -> OperatingPointResult:
    """Parse required supply/node values and optional MOS operating quantities."""
    required_rows = _read_numeric_rows(Path(op_output_path))
    values = required_rows[-1]
    if len(values) < 4:
        raise ParseError(f"operating-point output requires at least 4 values, found {len(values)}")
    required = values[-4:]
    optional_names = ("vgs", "vds", "gm", "gds", "vth", "vdsat")
    optional: dict[str, float] = {}
    unsupported: tuple[str, ...] = optional_names
    if device_op_output_path is not None and Path(device_op_output_path).is_file():
        device_values = _read_numeric_rows(Path(device_op_output_path))[-1]
        if len(device_values) >= len(optional_names):
            optional = dict(zip(optional_names, device_values[-len(optional_names):]))
            unsupported = ()
    return OperatingPointResult(
        supply_voltage_v=required[0],
        input_voltage_v=required[1],
        output_voltage_v=required[2],
        supply_current_a=required[3],
        device_quantities=optional,
        unsupported_device_quantities=unsupported,
    )


def analyze_common_source(
    ac_response: ACAnalysisResult, operating_point: OperatingPointResult
) -> CommonSourceMetrics:
    """Extract gain, bandwidth, real supply power, and bias from parsed evidence."""
    if len(ac_response) < 2:
        raise AnalysisError("common-source AC response requires at least two samples")
    gain = float(ac_response.gain_db[0])
    peak = max(float(value) for value in ac_response.gain_db)
    bandwidth = find_cutoff_frequency(ac_response.frequency_hz, ac_response.gain_db)
    power = dc_supply_power(
        operating_point.supply_voltage_v, operating_point.supply_current_a
    )
    return CommonSourceMetrics(
        low_frequency_gain_db=gain,
        peak_gain_db=peak,
        bandwidth_3db_hz=bandwidth,
        dc_power_w=power,
        output_dc_voltage=operating_point.output_voltage_v,
        supply_current_a=operating_point.supply_current_a,
    )
