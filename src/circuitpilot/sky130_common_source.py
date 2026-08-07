"""Independent SKY130 common-source benchmark topology and runtime paths."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from math import isfinite
import os
from pathlib import Path
import string
import subprocess
from typing import Any, Iterator, Mapping

from circuitpilot.bandwidth import BANDWIDTH_SEMANTICS_VERSION
from circuitpilot.exceptions import ConfigError, NetlistError, SimulationError
from circuitpilot.sky130_model import Sky130ModelConfig, sky130_model_from_mapping


SKY130_COMMON_SOURCE_PARAMETER_NAMES = {
    "width_m",
    "length_m",
    "drain_resistance_ohm",
    "input_bias_v",
}
CENSORING_POLICY = "fixed_window_right_censored_lower_bound_v1"
DIFFICULTY_PROTOCOL_VERSION = "task4_sky130_difficulty_v1"


@dataclass(frozen=True, slots=True)
class Sky130CommonSourceCircuitConfig:
    """All fixed electrical and measurement semantics for Task 4."""

    supply_voltage_v: float
    load_capacitance_f: float
    temperature_c: float
    model: Sky130ModelConfig
    bandwidth_semantics_version: str = BANDWIDTH_SEMANTICS_VERSION
    censoring_policy: str = CENSORING_POLICY
    difficulty_protocol_version: str = DIFFICULTY_PROTOCOL_VERSION

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
        if not 0 < self.supply_voltage_v <= 1.8:
            raise ValueError("SKY130 01v8 benchmark supply must be in (0, 1.8] V")
        if self.load_capacitance_f <= 0:
            raise ValueError("circuit_config.load_capacitance_f must be positive")
        if not isinstance(self.model, Sky130ModelConfig):
            raise ValueError("circuit_config.sky130_model must be Sky130ModelConfig")
        if self.bandwidth_semantics_version != BANDWIDTH_SEMANTICS_VERSION:
            raise ValueError("unsupported Task 4 bandwidth_semantics_version")
        if self.censoring_policy != CENSORING_POLICY:
            raise ValueError("unsupported Task 4 censoring_policy")
        if self.difficulty_protocol_version != DIFFICULTY_PROTOCOL_VERSION:
            raise ValueError("unsupported Task 4 difficulty_protocol_version")

    def to_dict(self) -> dict[str, Any]:
        """Return every fixed value used for manifests and benchmark hashing."""
        return {
            "supply_voltage_v": self.supply_voltage_v,
            "load_capacitance_f": self.load_capacitance_f,
            "temperature_c": self.temperature_c,
            "bandwidth_semantics_version": self.bandwidth_semantics_version,
            "censoring_policy": self.censoring_policy,
            "difficulty_protocol_version": self.difficulty_protocol_version,
            "sky130_model": self.model.to_dict(),
        }


def sky130_common_source_config_from_mapping(
    value: Mapping[str, Any], *, base_directory: Path | None = None
) -> Sky130CommonSourceCircuitConfig:
    """Parse strict fixed Task 4 topology/model values from YAML."""
    if not isinstance(value, Mapping):
        raise ConfigError("circuit_config must be a YAML mapping")
    required = {
        "supply_voltage_v",
        "load_capacitance_f",
        "temperature_c",
        "sky130_model",
        "bandwidth_semantics_version",
        "censoring_policy",
        "difficulty_protocol_version",
    }
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    if missing:
        raise ConfigError(f"circuit_config is missing required field(s): {', '.join(missing)}")
    if unknown:
        raise ConfigError(f"circuit_config contains unknown field(s): {', '.join(unknown)}")
    try:
        return Sky130CommonSourceCircuitConfig(
            supply_voltage_v=float(value["supply_voltage_v"]),
            load_capacitance_f=float(value["load_capacitance_f"]),
            temperature_c=float(value["temperature_c"]),
            model=sky130_model_from_mapping(
                value["sky130_model"], base_directory=base_directory
            ),
            bandwidth_semantics_version=value["bandwidth_semantics_version"],
            censoring_policy=value["censoring_policy"],
            difficulty_protocol_version=value["difficulty_protocol_version"],
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(str(exc)) from exc


def _safe_spice_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    if '"' in normalized or "\n" in normalized or "\r" in normalized:
        raise NetlistError("ngspice paths cannot contain quotes or newlines")
    return normalized


def generate_sky130_common_source_netlist(
    config: Sky130CommonSourceCircuitConfig,
    parameters: Mapping[str, float | int],
    *,
    invariant_path: str,
    corner_path: str,
    ac_output_path: str,
    op_output_path: str,
    device_op_output_path: str,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
) -> str:
    """Generate one real SKY130 `.op` + fixed-window `.ac` netlist."""
    if set(parameters) != SKY130_COMMON_SOURCE_PARAMETER_NAMES:
        raise NetlistError(
            "SKY130 common-source parameters must be width_m, length_m, "
            "drain_resistance_ohm, and input_bias_v"
        )
    width_m = float(parameters["width_m"])
    length_m = float(parameters["length_m"])
    resistance = float(parameters["drain_resistance_ohm"])
    bias = float(parameters["input_bias_v"])
    numeric = (
        width_m,
        length_m,
        resistance,
        bias,
        start_frequency_hz,
        stop_frequency_hz,
    )
    if not all(isfinite(item) for item in numeric):
        raise NetlistError("SKY130 common-source values must be finite")
    if width_m <= 0 or length_m <= 0 or resistance <= 0:
        raise NetlistError("SKY130 W, L, and RD must be positive")
    if not 0 <= bias <= config.supply_voltage_v:
        raise NetlistError("input_bias_v must be between ground and VDD")
    if start_frequency_hz <= 0 or stop_frequency_hz <= start_frequency_hz:
        raise NetlistError("invalid fixed AC measurement window")
    if points_per_decade < 2:
        raise NetlistError("points_per_decade must be at least 2")
    width_um = width_m * 1e6
    length_um = length_m * 1e6
    paths = {
        name: _safe_spice_path(path)
        for name, path in {
            "invariant": invariant_path,
            "corner": corner_path,
            "ac": ac_output_path,
            "op": op_output_path,
            "device": device_op_output_path,
        }.items()
    }
    internal = "m.x1.msky130_fd_pr__nfet_01v8"
    return "\n".join(
        (
            "* CircuitPilot Task 4 SKY130 common-source benchmark",
            ".option scale=1u",
            ".param mc_mm_switch=0 mc_pr_switch=0",
            f'.include "{paths["invariant"]}"',
            f'.include "{paths["corner"]}"',
            f".temp {config.temperature_c:.12g}",
            f"VDD vdd 0 DC {config.supply_voltage_v:.12g}",
            f"VIN in 0 DC {bias:.12g} AC 1",
            f"RD vdd out {resistance:.12g}",
            # Drain, gate, source, and bulk are all explicit.
            f"X1 out in 0 0 {config.model.device_name} W={width_um:.12g} L={length_um:.12g}",
            f"CL out 0 {config.load_capacitance_f:.12g}",
            ".control",
            "set wr_singlescale",
            "set wr_vecnames",
            "op",
            f'wrdata {paths["op"]} v(vdd) v(in) v(out) i(vdd)',
            f'wrdata {paths["device"]} '
            f"@{internal}[vgs] @{internal}[vds] @{internal}[gm] "
            f"@{internal}[gds] @{internal}[vth] @{internal}[vdsat]",
            f"ac dec {points_per_decade} {start_frequency_hz:.12g} {stop_frequency_hz:.12g}",
            f'wrdata {paths["ac"]} vdb(out) vp(out)',
            "quit",
            ".endc",
            ".end",
            "",
        )
    )


@dataclass(frozen=True, slots=True)
class NgspiceRuntimePaths:
    """Physical artifact paths plus short paths visible to Windows ngspice."""

    netlist_path: Path
    ac_path: Path
    op_path: Path
    device_path: Path
    log_path: Path
    runtime_netlist: Path
    runtime_ac: str
    runtime_op: str
    runtime_device: str
    runtime_log: Path
    runtime_invariant: str
    runtime_corner: str


def _run_subst(arguments: list[str], *, tolerate_missing: bool = False) -> None:
    completed = subprocess.run(
        ["subst", *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0 and not tolerate_missing:
        detail = (completed.stderr or completed.stdout).strip()
        raise SimulationError(
            f"failed to create Windows short-path mapping: {detail or completed.returncode}"
        )


def _available_drive_letters(count: int) -> list[str]:
    available = []
    for letter in reversed(string.ascii_uppercase):
        root = Path(f"{letter}:\\")
        if not root.exists():
            available.append(f"{letter}:")
            if len(available) == count:
                return available
    raise SimulationError("not enough unused Windows drive letters for ngspice aliases")


@contextmanager
def sky130_runtime_paths(
    model: Sky130ModelConfig, evaluation_directory: Path
) -> Iterator[NgspiceRuntimePaths]:
    """Expose ASCII/short ngspice paths while preserving physical artifacts."""
    directory = evaluation_directory.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    # Keep evidence names compact because a suite run adds several nested,
    # immutable IDs.  Windows may reject a perfectly valid artifact once the
    # full path exceeds MAX_PATH even though ngspice itself uses a short alias.
    netlist = directory / "circuit.cir"
    ac_path = directory / "ac.dat"
    op_path = directory / "op.dat"
    device_path = directory / "device_op.dat"
    log_path = directory / "ngspice.log"
    if os.name != "nt":
        yield NgspiceRuntimePaths(
            netlist,
            ac_path,
            op_path,
            device_path,
            log_path,
            netlist,
            ac_path.name,
            op_path.name,
            device_path.name,
            log_path,
            model.invariant_path.as_posix(),
            model.corner_path.as_posix(),
        )
        return

    pdk_drive, run_drive = _available_drive_letters(2)
    created: list[str] = []
    try:
        _run_subst([pdk_drive, str(model.pdk_root)])
        created.append(pdk_drive)
        _run_subst([run_drive, str(directory)])
        created.append(run_drive)
        pdk_prefix = f"{pdk_drive}/".replace(":/", ":/")
        run_prefix = f"{run_drive}/".replace(":/", ":/")
        yield NgspiceRuntimePaths(
            netlist,
            ac_path,
            op_path,
            device_path,
            log_path,
            Path(f"{run_drive}\\{netlist.name}"),
            f"{run_prefix}{ac_path.name}",
            f"{run_prefix}{op_path.name}",
            f"{run_prefix}{device_path.name}",
            Path(f"{run_drive}\\{log_path.name}"),
            f"{pdk_prefix}libs.tech/ngspice/parameters/invariant.spice",
            f"{pdk_prefix}libs.ref/sky130_fd_pr/spice/sky130_fd_pr__nfet_01v8__tt.corner.spice",
        )
    finally:
        for drive in reversed(created):
            _run_subst([drive, "/D"], tolerate_missing=True)
