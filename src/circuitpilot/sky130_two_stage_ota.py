"""Real-SKY130 two-stage Miller OTA benchmark for Research Task 7."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite, log10
import os
from pathlib import Path
import re
from time import monotonic
from typing import Any, Mapping, Sequence

from circuitpilot.analysis import find_cutoff_frequency
from circuitpilot.exceptions import AnalysisError, ConfigError, NetlistError, ParseError
from circuitpilot.parser import ACAnalysisResult, parse_ac_output
from circuitpilot.simulator import SimulationResult, run_ngspice
from circuitpilot.sky130_common_source import sky130_runtime_paths
from circuitpilot.sky130_model import (
    SKY130_DEVICE_NAME,
    SKY130_PFET_DEVICE_NAME,
    Sky130ModelConfig,
    sky130_model_from_mapping,
)


TASK7_PARAMETER_NAMES = {
    "input_pair_width_m",
    "input_pair_length_m",
    "first_stage_load_width_m",
    "first_stage_load_length_m",
    "tail_width_m",
    "tail_length_m",
    "second_stage_width_m",
    "second_stage_length_m",
    "second_load_width_m",
    "second_load_length_m",
    "second_load_bias_v",
    "compensation_capacitance_f",
}
TOPOLOGY_VERSION = "sky130_two_stage_miller_ota_v1"
DEVICE_ROLE_MAPPING_VERSION = "task7_role_matched_12d_prior_v1"
AC_TESTBENCH_VERSION = "task7_opposed_half_volt_unit_differential_v1"
UGF_SEMANTICS_VERSION = "task7_first_descending_zero_db_log_interpolation_v1"
PHASE_MARGIN_SEMANTICS_VERSION = "task7_unwrapped_phase_at_same_first_ugf_v1"
TRANSIENT_TESTBENCH_VERSION = "task7_unity_follower_fixed_0p8_1p0v_step_v1"
SLEW_SEMANTICS_VERSION = "task7_fixed_20_80pct_crossing_interpolation_v1"
OP_RULES_VERSION = "task7_explicit_voltage_inequalities_all_seven_devices_v1"
COST_SEMANTICS_VERSION = "task7_full_three_independent_processes_v1"

DEVICE_ROLES = (
    "input_minus",
    "input_plus",
    "load_mirror",
    "load_first",
    "tail",
    "second_stage",
    "second_load",
)
PFET_ROLES = frozenset({"load_mirror", "load_first", "second_load"})
DEVICE_ROLE_MAPPING = {
    "input_minus": {
        "device": SKY130_DEVICE_NAME,
        "size_role": "input_pair",
        "nodes": ("mirror", "vin_minus", "tail", "gnd"),
    },
    "input_plus": {
        "device": SKY130_DEVICE_NAME,
        "size_role": "input_pair",
        "nodes": ("stage1_out", "vin_plus", "tail", "gnd"),
    },
    "load_mirror": {
        "device": SKY130_PFET_DEVICE_NAME,
        "size_role": "first_stage_load",
        "nodes": ("mirror", "mirror", "vdd", "vdd"),
    },
    "load_first": {
        "device": SKY130_PFET_DEVICE_NAME,
        "size_role": "first_stage_load",
        "nodes": ("stage1_out", "mirror", "vdd", "vdd"),
    },
    "tail": {
        "device": SKY130_DEVICE_NAME,
        "size_role": "tail",
        "nodes": ("tail", "tail_bias", "gnd", "gnd"),
    },
    "second_stage": {
        "device": SKY130_DEVICE_NAME,
        "size_role": "second_stage",
        "nodes": ("vout", "stage1_out", "gnd", "gnd"),
    },
    "second_load": {
        "device": SKY130_PFET_DEVICE_NAME,
        "size_role": "second_load",
        "nodes": ("vout", "second_load_bias", "vdd", "vdd"),
    },
}


@dataclass(frozen=True, slots=True)
class Sky130TwoStageOtaCircuitConfig:
    """Frozen electrical conditions and versioned measurement semantics."""

    supply_voltage_v: float
    input_common_mode_v: float
    tail_bias_v: float
    load_capacitance_f: float
    temperature_c: float
    transient_low_v: float
    transient_high_v: float
    transient_rise_time_s: float
    transient_fall_time_s: float
    transient_rising_edge_s: float
    transient_falling_edge_s: float
    transient_stop_time_s: float
    transient_max_step_s: float
    transient_edge_exclusion_s: float
    slew_lower_fraction: float
    slew_upper_fraction: float
    model: Sky130ModelConfig
    nfet_device_name: str = SKY130_DEVICE_NAME
    pfet_device_name: str = SKY130_PFET_DEVICE_NAME
    topology_version: str = TOPOLOGY_VERSION
    device_role_mapping_version: str = DEVICE_ROLE_MAPPING_VERSION
    ac_testbench_version: str = AC_TESTBENCH_VERSION
    ugf_semantics_version: str = UGF_SEMANTICS_VERSION
    phase_margin_semantics_version: str = PHASE_MARGIN_SEMANTICS_VERSION
    transient_testbench_version: str = TRANSIENT_TESTBENCH_VERSION
    slew_semantics_version: str = SLEW_SEMANTICS_VERSION
    op_rules_version: str = OP_RULES_VERSION
    cost_semantics_version: str = COST_SEMANTICS_VERSION

    def __post_init__(self) -> None:
        numeric_names = (
            "supply_voltage_v",
            "input_common_mode_v",
            "tail_bias_v",
            "load_capacitance_f",
            "temperature_c",
            "transient_low_v",
            "transient_high_v",
            "transient_rise_time_s",
            "transient_fall_time_s",
            "transient_rising_edge_s",
            "transient_falling_edge_s",
            "transient_stop_time_s",
            "transient_max_step_s",
            "transient_edge_exclusion_s",
            "slew_lower_fraction",
            "slew_upper_fraction",
        )
        numeric = {name: float(getattr(self, name)) for name in numeric_names}
        if not all(isfinite(value) for value in numeric.values()):
            raise ValueError("Task 7 circuit values must be finite")
        if not 0 < self.supply_voltage_v <= 1.8:
            raise ValueError("Task 7 SKY130 01v8 supply must be in (0, 1.8]")
        for name in (
            "input_common_mode_v",
            "tail_bias_v",
            "transient_low_v",
            "transient_high_v",
        ):
            if not 0 < numeric[name] < self.supply_voltage_v:
                raise ValueError(f"{name} must be strictly inside the supply rails")
        if not self.transient_low_v < self.transient_high_v:
            raise ValueError("transient_low_v must be below transient_high_v")
        if self.load_capacitance_f <= 0:
            raise ValueError("load_capacitance_f must be positive")
        for name in (
            "transient_rise_time_s",
            "transient_fall_time_s",
            "transient_rising_edge_s",
            "transient_falling_edge_s",
            "transient_stop_time_s",
            "transient_max_step_s",
            "transient_edge_exclusion_s",
        ):
            if numeric[name] <= 0:
                raise ValueError(f"{name} must be positive")
        if not (
            self.transient_rising_edge_s
            < self.transient_falling_edge_s
            < self.transient_stop_time_s
        ):
            raise ValueError("transient edges and stop time must be increasing")
        if not 0 < self.slew_lower_fraction < self.slew_upper_fraction < 1:
            raise ValueError("slew fractions must satisfy 0 < lower < upper < 1")
        if not isinstance(self.model, Sky130ModelConfig):
            raise ValueError("sky130_model must be a Sky130ModelConfig")
        expected = {
            "nfet_device_name": SKY130_DEVICE_NAME,
            "pfet_device_name": SKY130_PFET_DEVICE_NAME,
            "topology_version": TOPOLOGY_VERSION,
            "device_role_mapping_version": DEVICE_ROLE_MAPPING_VERSION,
            "ac_testbench_version": AC_TESTBENCH_VERSION,
            "ugf_semantics_version": UGF_SEMANTICS_VERSION,
            "phase_margin_semantics_version": PHASE_MARGIN_SEMANTICS_VERSION,
            "transient_testbench_version": TRANSIENT_TESTBENCH_VERSION,
            "slew_semantics_version": SLEW_SEMANTICS_VERSION,
            "op_rules_version": OP_RULES_VERSION,
            "cost_semantics_version": COST_SEMANTICS_VERSION,
        }
        for name, required in expected.items():
            if getattr(self, name) != required:
                raise ValueError(f"unsupported Task 7 {name}")

    def to_dict(self) -> dict[str, Any]:
        result = {
            name: getattr(self, name)
            for name in (
                "supply_voltage_v",
                "input_common_mode_v",
                "tail_bias_v",
                "load_capacitance_f",
                "temperature_c",
                "transient_low_v",
                "transient_high_v",
                "transient_rise_time_s",
                "transient_fall_time_s",
                "transient_rising_edge_s",
                "transient_falling_edge_s",
                "transient_stop_time_s",
                "transient_max_step_s",
                "transient_edge_exclusion_s",
                "slew_lower_fraction",
                "slew_upper_fraction",
                "nfet_device_name",
                "pfet_device_name",
                "topology_version",
                "device_role_mapping_version",
                "ac_testbench_version",
                "ugf_semantics_version",
                "phase_margin_semantics_version",
                "transient_testbench_version",
                "slew_semantics_version",
                "op_rules_version",
                "cost_semantics_version",
            )
        }
        result["topology_definition"] = {
            "kind": "seven_transistor_two_stage_single_ended_miller_ota",
            "first_stage": "NMOS differential pair with 1:1 PMOS mirror load",
            "second_stage": "NMOS common source with PMOS voltage-biased load",
            "compensation": "Cc between stage1_out and vout",
            "load": "CL between vout and ground",
        }
        result["device_role_mapping"] = DEVICE_ROLE_MAPPING
        result["cost_definition"] = {
            "candidate_evaluations_per_candidate": 1,
            "ngspice_process_calls_per_candidate": 3,
            "op_calls_per_candidate": 1,
            "ac_calls_per_candidate": 1,
            "transient_calls_per_candidate": 1,
            "high_fidelity_analysis_calls_per_candidate": 3,
            "screening_calls_per_candidate": 0,
        }
        result["sky130_model"] = self.model.to_dict()
        return result


def sky130_two_stage_ota_config_from_mapping(
    value: Mapping[str, Any], *, base_directory: Path | None = None
) -> Sky130TwoStageOtaCircuitConfig:
    if not isinstance(value, Mapping):
        raise ConfigError("circuit_config must be a YAML mapping")
    version_names = {
        "nfet_device_name",
        "pfet_device_name",
        "topology_version",
        "device_role_mapping_version",
        "ac_testbench_version",
        "ugf_semantics_version",
        "phase_margin_semantics_version",
        "transient_testbench_version",
        "slew_semantics_version",
        "op_rules_version",
        "cost_semantics_version",
    }
    numeric_names = {
        "supply_voltage_v",
        "input_common_mode_v",
        "tail_bias_v",
        "load_capacitance_f",
        "temperature_c",
        "transient_low_v",
        "transient_high_v",
        "transient_rise_time_s",
        "transient_fall_time_s",
        "transient_rising_edge_s",
        "transient_falling_edge_s",
        "transient_stop_time_s",
        "transient_max_step_s",
        "transient_edge_exclusion_s",
        "slew_lower_fraction",
        "slew_upper_fraction",
    }
    required = version_names | numeric_names | {"sky130_model"}
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    if missing:
        raise ConfigError(f"circuit_config is missing required field(s): {', '.join(missing)}")
    if unknown:
        raise ConfigError(f"circuit_config contains unknown field(s): {', '.join(unknown)}")
    try:
        return Sky130TwoStageOtaCircuitConfig(
            **{name: float(value[name]) for name in numeric_names},
            **{name: value[name] for name in version_names},
            model=sky130_model_from_mapping(
                value["sky130_model"], base_directory=base_directory
            ),
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(str(exc)) from exc


def _safe_spice_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    if '"' in normalized or "\n" in normalized or "\r" in normalized:
        raise NetlistError("ngspice paths cannot contain quotes or newlines")
    return normalized


def _candidate_values(parameters: Mapping[str, float | int]) -> dict[str, float]:
    if set(parameters) != TASK7_PARAMETER_NAMES:
        raise NetlistError("Task 7 parameters must match the frozen twelve dimensions")
    values = {name: float(parameters[name]) for name in TASK7_PARAMETER_NAMES}
    if not all(isfinite(value) for value in values.values()):
        raise NetlistError("Task 7 candidate values must be finite")
    for name, value in values.items():
        if name != "second_load_bias_v" and value <= 0:
            raise NetlistError(f"{name} must be positive")
    return values


def _device_lines(
    config: Sky130TwoStageOtaCircuitConfig,
    parameters: Mapping[str, float | int],
) -> tuple[str, ...]:
    values = _candidate_values(parameters)
    um = {name: value * 1e6 for name, value in values.items() if name.endswith("_m")}
    return (
        f"XM1 mirror vin_minus tail 0 {config.nfet_device_name} "
        f"W={um['input_pair_width_m']:.12g} L={um['input_pair_length_m']:.12g}",
        f"XM2 stage1_out vin_plus tail 0 {config.nfet_device_name} "
        f"W={um['input_pair_width_m']:.12g} L={um['input_pair_length_m']:.12g}",
        f"XM3 mirror mirror vdd vdd {config.pfet_device_name} "
        f"W={um['first_stage_load_width_m']:.12g} "
        f"L={um['first_stage_load_length_m']:.12g}",
        f"XM4 stage1_out mirror vdd vdd {config.pfet_device_name} "
        f"W={um['first_stage_load_width_m']:.12g} "
        f"L={um['first_stage_load_length_m']:.12g}",
        f"XM5 tail tail_bias 0 0 {config.nfet_device_name} "
        f"W={um['tail_width_m']:.12g} L={um['tail_length_m']:.12g}",
        f"XM6 vout stage1_out 0 0 {config.nfet_device_name} "
        f"W={um['second_stage_width_m']:.12g} L={um['second_stage_length_m']:.12g}",
        f"XM7 vout second_load_bias vdd vdd {config.pfet_device_name} "
        f"W={um['second_load_width_m']:.12g} L={um['second_load_length_m']:.12g}",
        f"CC stage1_out vout {values['compensation_capacitance_f']:.12g}",
        f"CL vout 0 {config.load_capacitance_f:.12g}",
    )


def _preamble(
    config: Sky130TwoStageOtaCircuitConfig,
    *,
    invariant_path: str,
    nfet_corner_path: str,
    pfet_corner_path: str,
) -> list[str]:
    paths = tuple(
        _safe_spice_path(path)
        for path in (invariant_path, nfet_corner_path, pfet_corner_path)
    )
    return [
        "* CircuitPilot Research Task 7 real SKY130 two-stage Miller OTA",
        ".option scale=1u",
        ".param mc_mm_switch=0 mc_pr_switch=0",
        f'.include "{paths[0]}"',
        f'.include "{paths[1]}"',
        f'.include "{paths[2]}"',
        f".temp {config.temperature_c:.12g}",
        f"VDD vdd 0 DC {config.supply_voltage_v:.12g}",
        f"VTAIL tail_bias 0 DC {config.tail_bias_v:.12g}",
    ]


def _device_vector(role_index: int, device: str) -> str:
    internal = f"m.xm{role_index}.m{device}"
    return " ".join(
        f"@{internal}[{quantity}]"
        for quantity in ("vgs", "vds", "gm", "gds", "vth", "vdsat")
    )


def generate_task7_op_netlist(
    config: Sky130TwoStageOtaCircuitConfig,
    parameters: Mapping[str, float | int],
    *,
    invariant_path: str,
    nfet_corner_path: str,
    pfet_corner_path: str,
    op_output_path: str,
    device_op_output_path: str,
) -> str:
    values = _candidate_values(parameters)
    op_path = _safe_spice_path(op_output_path)
    device_path = _safe_spice_path(device_op_output_path)
    device_vectors = " ".join(
        _device_vector(
            index,
            config.pfet_device_name if role in PFET_ROLES else config.nfet_device_name,
        )
        for index, role in enumerate(DEVICE_ROLES, start=1)
    )
    lines = [
        *_preamble(
            config,
            invariant_path=invariant_path,
            nfet_corner_path=nfet_corner_path,
            pfet_corner_path=pfet_corner_path,
        ),
        f"VINP vin_plus 0 DC {config.input_common_mode_v:.12g}",
        f"VINN vin_minus 0 DC {config.input_common_mode_v:.12g}",
        f"VLOADBIAS second_load_bias 0 DC {values['second_load_bias_v']:.12g}",
        *_device_lines(config, values),
        ".control",
        "set wr_singlescale",
        "set wr_vecnames",
        "op",
        f"wrdata {op_path} v(vdd) v(vin_plus) v(vin_minus) v(stage1_out) "
        "v(vout) v(tail) v(tail_bias) v(second_load_bias) i(VDD)",
        f"wrdata {device_path} {device_vectors}",
        "quit",
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


def generate_task7_ac_netlist(
    config: Sky130TwoStageOtaCircuitConfig,
    parameters: Mapping[str, float | int],
    *,
    invariant_path: str,
    nfet_corner_path: str,
    pfet_corner_path: str,
    ac_output_path: str,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
) -> str:
    values = _candidate_values(parameters)
    if start_frequency_hz <= 0 or stop_frequency_hz <= start_frequency_hz:
        raise NetlistError("invalid Task 7 AC frequency window")
    if points_per_decade < 2:
        raise NetlistError("Task 7 AC points_per_decade must be at least 2")
    output = _safe_spice_path(ac_output_path)
    lines = [
        *_preamble(
            config,
            invariant_path=invariant_path,
            nfet_corner_path=nfet_corner_path,
            pfet_corner_path=pfet_corner_path,
        ),
        f"VINP vin_plus 0 DC {config.input_common_mode_v:.12g} AC 0.5 0",
        f"VINN vin_minus 0 DC {config.input_common_mode_v:.12g} AC 0.5 180",
        f"VLOADBIAS second_load_bias 0 DC {values['second_load_bias_v']:.12g}",
        *_device_lines(config, values),
        ".control",
        "set wr_singlescale",
        "set wr_vecnames",
        f"ac dec {points_per_decade} {start_frequency_hz:.12g} {stop_frequency_hz:.12g}",
        f"wrdata {output} vdb(vout) 180/pi*vp(vout)",
        "quit",
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


def generate_task7_transient_netlist(
    config: Sky130TwoStageOtaCircuitConfig,
    parameters: Mapping[str, float | int],
    *,
    invariant_path: str,
    nfet_corner_path: str,
    pfet_corner_path: str,
    transient_output_path: str,
) -> str:
    values = _candidate_values(parameters)
    output = _safe_spice_path(transient_output_path)
    high_duration = (
        config.transient_falling_edge_s
        - config.transient_rising_edge_s
        - config.transient_rise_time_s
    )
    if high_duration <= 0:
        raise NetlistError("transient pulse width must be positive")
    lines = [
        *_preamble(
            config,
            invariant_path=invariant_path,
            nfet_corner_path=nfet_corner_path,
            pfet_corner_path=pfet_corner_path,
        ),
        "VINP command 0 PULSE("
        f"{config.transient_low_v:.12g} {config.transient_high_v:.12g} "
        f"{config.transient_rising_edge_s:.12g} {config.transient_rise_time_s:.12g} "
        f"{config.transient_fall_time_s:.12g} {high_duration:.12g} "
        f"{config.transient_stop_time_s * 2.0:.12g})",
        "VFB vin_minus vout 0",
        "ECMD vin_plus 0 command 0 1",
        f"VLOADBIAS second_load_bias 0 DC {values['second_load_bias_v']:.12g}",
        *_device_lines(config, values),
        ".control",
        "set wr_singlescale",
        "set wr_vecnames",
        f"tran {config.transient_max_step_s:.12g} {config.transient_stop_time_s:.12g} "
        f"0 {config.transient_max_step_s:.12g}",
        f"wrdata {output} v(command) v(vout)",
        "quit",
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


_SEPARATOR = re.compile(r"[\s,]+")


def _numeric_rows(path: str | Path, expected_columns: int | None = None) -> list[list[float]]:
    source = Path(path).resolve()
    try:
        lines = source.read_text(encoding="utf-8", errors="strict").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ParseError(f"failed to read Task 7 output '{source}': {exc}") from exc
    rows: list[list[float]] = []
    for line_number, raw in enumerate(lines, start=1):
        text = raw.strip()
        if not text or text.startswith(("#", "*")):
            continue
        tokens = [token for token in _SEPARATOR.split(text) if token]
        try:
            values = [
                float(token.replace("D", "E").replace("d", "e"))
                for token in tokens
            ]
        except ValueError:
            if not rows:
                continue
            raise ParseError(f"invalid Task 7 numeric data at line {line_number}") from None
        if not all(isfinite(value) for value in values):
            raise ParseError(f"non-finite Task 7 data at line {line_number}")
        if expected_columns is not None and len(values) != expected_columns:
            raise ParseError(
                f"expected {expected_columns} columns at line {line_number}, found {len(values)}"
            )
        rows.append(values)
    if not rows:
        raise ParseError(f"Task 7 output contains no data rows: '{source}'")
    return rows


@dataclass(frozen=True, slots=True)
class Task7OperatingPoint:
    supply_voltage_v: float
    input_positive_voltage_v: float
    input_negative_voltage_v: float
    stage1_voltage_v: float
    output_voltage_v: float
    tail_voltage_v: float
    tail_bias_v: float
    second_load_bias_v: float
    supply_current_a: float
    dc_power_w: float
    device_quantities: Mapping[str, Mapping[str, float]]


def parse_task7_operating_point(
    op_output_path: str | Path, device_op_output_path: str | Path
) -> Task7OperatingPoint:
    op_rows = _numeric_rows(op_output_path)
    if len(op_rows[-1]) < 9:
        raise ParseError("Task 7 operating point requires nine values")
    values = op_rows[-1][-9:]
    quantities = ("vgs", "vds", "gm", "gds", "vth", "vdsat")
    device_rows = _numeric_rows(device_op_output_path)
    required = len(DEVICE_ROLES) * len(quantities)
    if len(device_rows[-1]) < required:
        raise ParseError(f"Task 7 device operating point requires {required} values")
    raw = device_rows[-1][-required:]
    devices = {
        role: dict(zip(quantities, raw[index * 6 : (index + 1) * 6]))
        for index, role in enumerate(DEVICE_ROLES)
    }
    current = abs(float(values[8]))
    return Task7OperatingPoint(
        supply_voltage_v=float(values[0]),
        input_positive_voltage_v=float(values[1]),
        input_negative_voltage_v=float(values[2]),
        stage1_voltage_v=float(values[3]),
        output_voltage_v=float(values[4]),
        tail_voltage_v=float(values[5]),
        tail_bias_v=float(values[6]),
        second_load_bias_v=float(values[7]),
        supply_current_a=current,
        dc_power_w=abs(float(values[0])) * current,
        device_quantities=devices,
    )


@dataclass(frozen=True, slots=True)
class OperatingRegionAssessment:
    valid: bool
    violation_mask: int
    violation_types: tuple[str, ...]
    device_status: Mapping[str, str]


def assess_task7_operating_regions(
    operating_point: Task7OperatingPoint,
) -> OperatingRegionAssessment:
    statuses: dict[str, str] = {}
    violations: list[str] = []
    mask = 0
    for index, role in enumerate(DEVICE_ROLES):
        values = operating_point.device_quantities.get(role, {})
        if not {"vgs", "vds", "vth", "gm", "gds", "vdsat"} <= set(values):
            status = "missing"
        elif not all(isfinite(float(value)) for value in values.values()):
            status = "non_finite"
        else:
            vgs = float(values["vgs"])
            vds = float(values["vds"])
            vth = float(values["vth"])
            if role in PFET_ROLES:
                overdrive = abs(vgs) - abs(vth)
                drain_headroom = abs(vds)
            else:
                overdrive = vgs - vth
                drain_headroom = vds
            if overdrive <= 0:
                status = "off"
            elif drain_headroom < overdrive:
                status = "triode"
            else:
                status = "saturation"
        statuses[role] = status
        if status != "saturation":
            mask |= 1 << index
            violations.append(f"{role}:{status}")
    return OperatingRegionAssessment(
        valid=not violations,
        violation_mask=mask,
        violation_types=tuple(violations),
        device_status=statuses,
    )


class UgfStatus(str, Enum):
    MEASURED = "measured"
    RIGHT_CENSORED = "right_censored"
    NO_CROSSING = "no_crossing"
    INVALID_RESPONSE = "invalid_response"
    ANALYSIS_ERROR = "analysis_error"


class PhaseMarginStatus(str, Enum):
    MEASURED = "measured"
    UNAVAILABLE = "unavailable"
    INVALID_RESPONSE = "invalid_response"
    ANALYSIS_ERROR = "analysis_error"


@dataclass(frozen=True, slots=True)
class StabilityMeasurement:
    ugf_status: UgfStatus
    phase_margin_status: PhaseMarginStatus
    dc_gain_db: float | None
    ugf_hz: float | None
    ugf_lower_bound_hz: float | None
    phase_margin_deg: float | None
    crossing_count: int
    unwrapped_phase_deg: tuple[float, ...]
    message: str | None = None


def _unwrap_phase_deg(values: Sequence[float]) -> tuple[float, ...]:
    if not values or not all(isfinite(float(value)) for value in values):
        raise AnalysisError("phase response must contain finite values")
    result = [((float(values[0]) + 180.0) % 360.0) - 180.0]
    for raw in values[1:]:
        principal = ((float(raw) + 180.0) % 360.0) - 180.0
        previous = result[-1]
        while principal - previous > 180.0:
            principal -= 360.0
        while principal - previous <= -180.0:
            principal += 360.0
        result.append(principal)
    return tuple(result)


def _invalid_stability(message: str) -> StabilityMeasurement:
    return StabilityMeasurement(
        UgfStatus.INVALID_RESPONSE,
        PhaseMarginStatus.INVALID_RESPONSE,
        None,
        None,
        None,
        None,
        0,
        (),
        message,
    )


def measure_task7_stability(response: ACAnalysisResult) -> StabilityMeasurement:
    frequency = response.frequency_hz
    gain = response.gain_db
    phase = response.phase_deg
    if len(frequency) != len(gain) or len(gain) != len(phase) or len(gain) < 2:
        return _invalid_stability("AC arrays must have equal length of at least two")
    previous = 0.0
    for f_hz, gain_db, phase_deg in zip(frequency, gain, phase):
        if (
            not isfinite(float(f_hz))
            or float(f_hz) <= previous
            or not isfinite(float(gain_db))
            or not isfinite(float(phase_deg))
        ):
            return _invalid_stability(
                "AC response must be finite with positive increasing frequency"
            )
        previous = float(f_hz)
    try:
        unwrapped = _unwrap_phase_deg(phase)
    except AnalysisError as exc:
        return _invalid_stability(str(exc))
    dc_gain = float(gain[0])
    if abs(unwrapped[0]) > 90.0:
        result = _invalid_stability(
            "low-frequency polarity is inconsistent with the frozen non-inverting path"
        )
        return StabilityMeasurement(
            result.ugf_status,
            result.phase_margin_status,
            dc_gain,
            None,
            None,
            None,
            0,
            unwrapped,
            result.message,
        )
    if dc_gain < 0.0:
        return StabilityMeasurement(
            UgfStatus.NO_CROSSING,
            PhaseMarginStatus.UNAVAILABLE,
            dc_gain,
            None,
            None,
            None,
            0,
            unwrapped,
            "low-frequency gain is already below unity",
        )
    crossings: list[tuple[int, float]] = []
    for index in range(1, len(gain)):
        upper = float(gain[index - 1])
        lower = float(gain[index])
        if upper >= 0.0 and lower < 0.0:
            fraction = (0.0 - upper) / (lower - upper)
            crossings.append((index, fraction))
    if not crossings:
        if float(gain[-1]) >= 0.0:
            return StabilityMeasurement(
                UgfStatus.RIGHT_CENSORED,
                PhaseMarginStatus.UNAVAILABLE,
                dc_gain,
                None,
                float(frequency[-1]),
                None,
                0,
                unwrapped,
                "gain remains at or above unity at the frozen stop frequency",
            )
        return StabilityMeasurement(
            UgfStatus.NO_CROSSING,
            PhaseMarginStatus.UNAVAILABLE,
            dc_gain,
            None,
            None,
            None,
            0,
            unwrapped,
            "no descending unity-gain crossing exists",
        )
    index, fraction = crossings[0]
    lower_log = log10(float(frequency[index - 1]))
    upper_log = log10(float(frequency[index]))
    ugf = 10.0 ** (lower_log + fraction * (upper_log - lower_log))
    phase_at_ugf = unwrapped[index - 1] + fraction * (
        unwrapped[index] - unwrapped[index - 1]
    )
    message = (
        None
        if len(crossings) == 1
        else f"{len(crossings)} descending crossings; first selected"
    )
    return StabilityMeasurement(
        UgfStatus.MEASURED,
        PhaseMarginStatus.MEASURED,
        dc_gain,
        ugf,
        None,
        180.0 + phase_at_ugf,
        len(crossings),
        unwrapped,
        message,
    )


@dataclass(frozen=True, slots=True)
class TransientResponse:
    time_s: tuple[float, ...]
    command_v: tuple[float, ...]
    output_v: tuple[float, ...]


def parse_task7_transient(path: str | Path) -> TransientResponse:
    rows = _numeric_rows(path, 3)
    time_s: list[float] = []
    command_v: list[float] = []
    output_v: list[float] = []
    previous = -1.0
    for index, row in enumerate(rows, start=1):
        if row[0] < 0 or row[0] <= previous:
            raise ParseError(f"transient time must be strictly increasing at row {index}")
        previous = row[0]
        time_s.append(row[0])
        command_v.append(row[1])
        output_v.append(row[2])
    return TransientResponse(tuple(time_s), tuple(command_v), tuple(output_v))


class SlewStatus(str, Enum):
    MEASURED = "measured"
    INSUFFICIENT_TRANSITION = "insufficient_transition"
    INVALID_RESPONSE = "invalid_response"
    ANALYSIS_ERROR = "analysis_error"


@dataclass(frozen=True, slots=True)
class SlewMeasurement:
    positive_status: SlewStatus
    negative_status: SlewStatus
    positive_slew_v_per_s: float | None
    negative_slew_v_per_s: float | None
    positive_crossing_times_s: tuple[float, float] | None
    negative_crossing_times_s: tuple[float, float] | None
    message: str | None = None


def _crossing_time(
    time_s: Sequence[float],
    values: Sequence[float],
    threshold: float,
    *,
    start_s: float,
    stop_s: float,
    rising: bool,
) -> float | None:
    for index in range(1, len(time_s)):
        t0, t1 = float(time_s[index - 1]), float(time_s[index])
        if t1 < start_s or t0 > stop_s:
            continue
        y0, y1 = float(values[index - 1]), float(values[index])
        crossed = y0 <= threshold < y1 if rising else y0 >= threshold > y1
        if not crossed:
            continue
        if y1 == y0:
            return t1
        fraction = (threshold - y0) / (y1 - y0)
        crossing = t0 + fraction * (t1 - t0)
        if start_s <= crossing <= stop_s:
            return crossing
    return None


def measure_task7_slew(
    response: TransientResponse, config: Sky130TwoStageOtaCircuitConfig
) -> SlewMeasurement:
    if (
        len(response.time_s) != len(response.command_v)
        or len(response.time_s) != len(response.output_v)
        or len(response.time_s) < 3
        or not all(
            isfinite(float(value))
            for series in (response.time_s, response.command_v, response.output_v)
            for value in series
        )
    ):
        return SlewMeasurement(
            SlewStatus.INVALID_RESPONSE,
            SlewStatus.INVALID_RESPONSE,
            None,
            None,
            None,
            None,
            "transient arrays must be finite, equal length, and contain at least three rows",
        )
    amplitude = config.transient_high_v - config.transient_low_v
    low_threshold = config.transient_low_v + config.slew_lower_fraction * amplitude
    high_threshold = config.transient_low_v + config.slew_upper_fraction * amplitude
    pos_start = config.transient_rising_edge_s + config.transient_edge_exclusion_s
    pos_stop = config.transient_falling_edge_s
    neg_start = config.transient_falling_edge_s + config.transient_edge_exclusion_s
    neg_stop = config.transient_stop_time_s
    pos_low = _crossing_time(
        response.time_s,
        response.output_v,
        low_threshold,
        start_s=pos_start,
        stop_s=pos_stop,
        rising=True,
    )
    pos_high = _crossing_time(
        response.time_s,
        response.output_v,
        high_threshold,
        start_s=pos_start,
        stop_s=pos_stop,
        rising=True,
    )
    neg_high = _crossing_time(
        response.time_s,
        response.output_v,
        high_threshold,
        start_s=neg_start,
        stop_s=neg_stop,
        rising=False,
    )
    neg_low = _crossing_time(
        response.time_s,
        response.output_v,
        low_threshold,
        start_s=neg_start,
        stop_s=neg_stop,
        rising=False,
    )
    pos_ok = pos_low is not None and pos_high is not None and pos_high > pos_low
    neg_ok = neg_high is not None and neg_low is not None and neg_low > neg_high
    delta_v = high_threshold - low_threshold
    return SlewMeasurement(
        SlewStatus.MEASURED if pos_ok else SlewStatus.INSUFFICIENT_TRANSITION,
        SlewStatus.MEASURED if neg_ok else SlewStatus.INSUFFICIENT_TRANSITION,
        delta_v / (pos_high - pos_low) if pos_ok else None,
        delta_v / (neg_low - neg_high) if neg_ok else None,
        (pos_low, pos_high) if pos_ok else None,
        (neg_high, neg_low) if neg_ok else None,
        None if pos_ok and neg_ok else "one or both fixed transitions were not completed",
    )


def optional_minus_3db_bandwidth(response: ACAnalysisResult) -> float | None:
    try:
        return find_cutoff_frequency(response.frequency_hz, response.gain_db)
    except AnalysisError:
        return None


@dataclass(frozen=True, slots=True)
class Task7AnalysisCost:
    candidate_evaluations: int
    ngspice_process_calls: int
    op_calls: int
    ac_calls: int
    transient_calls: int
    high_fidelity_analysis_calls: int
    op_runtime_seconds: float
    ac_runtime_seconds: float
    transient_runtime_seconds: float
    wall_clock_seconds: float


@dataclass(frozen=True, slots=True)
class Task7FullEvaluation:
    operating_point: Task7OperatingPoint | None
    operating_region: OperatingRegionAssessment | None
    ac_response: ACAnalysisResult | None
    stability: StabilityMeasurement
    transient_response: TransientResponse | None
    slew: SlewMeasurement
    metrics: Mapping[str, float | None]
    processes: Mapping[str, SimulationResult | None]
    errors: Mapping[str, str | None]
    cost: Task7AnalysisCost


def _write_netlist(path: Path, text: str) -> None:
    try:
        path.write_text(text, encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise NetlistError(f"failed to write Task 7 netlist '{path}': {exc}") from exc


def evaluate_task7_full_candidate(
    config: Sky130TwoStageOtaCircuitConfig,
    parameters: Mapping[str, float | int],
    evaluation_directory: Path,
    *,
    executable: str,
    timeout_seconds: float,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
) -> Task7FullEvaluation:
    """Attempt OP, AC, and transient independently for every candidate."""
    _candidate_values(parameters)
    root = evaluation_directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    started = monotonic()
    processes: dict[str, SimulationResult | None] = {
        "op": None,
        "ac": None,
        "transient": None,
    }
    errors: dict[str, str | None] = {"op": None, "ac": None, "transient": None}
    runtimes = {"op": 0.0, "ac": 0.0, "transient": 0.0}
    launches = {"op": 0, "ac": 0, "transient": 0}
    operating_point: Task7OperatingPoint | None = None
    region: OperatingRegionAssessment | None = None
    ac_response: ACAnalysisResult | None = None
    transient_response: TransientResponse | None = None
    stability = StabilityMeasurement(
        UgfStatus.ANALYSIS_ERROR,
        PhaseMarginStatus.ANALYSIS_ERROR,
        None,
        None,
        None,
        None,
        0,
        (),
        "AC analysis did not complete",
    )
    slew = SlewMeasurement(
        SlewStatus.ANALYSIS_ERROR,
        SlewStatus.ANALYSIS_ERROR,
        None,
        None,
        None,
        None,
        "transient analysis did not complete",
    )

    for kind in ("op", "ac", "transient"):
        directory = root / kind
        directory.mkdir(parents=True, exist_ok=True)
        analysis_started = monotonic()
        try:
            with sky130_runtime_paths(config.model, directory) as paths:
                windows_runtime = os.name == "nt"
                runtime_data = Path(paths.runtime_ac) if windows_runtime else paths.ac_path
                runtime_op = Path(paths.runtime_op) if windows_runtime else paths.op_path
                runtime_device = (
                    Path(paths.runtime_device) if windows_runtime else paths.device_path
                )
                for output in (
                    runtime_data,
                    runtime_op,
                    runtime_device,
                    paths.runtime_log,
                ):
                    output.unlink(missing_ok=True)
                common = {
                    "invariant_path": paths.runtime_invariant,
                    "nfet_corner_path": paths.runtime_corner,
                    "pfet_corner_path": paths.runtime_pfet_corner,
                }
                if kind == "op":
                    text = generate_task7_op_netlist(
                        config,
                        parameters,
                        **common,
                        op_output_path=paths.runtime_op,
                        device_op_output_path=paths.runtime_device,
                    )
                elif kind == "ac":
                    text = generate_task7_ac_netlist(
                        config,
                        parameters,
                        **common,
                        ac_output_path=paths.runtime_ac,
                        start_frequency_hz=start_frequency_hz,
                        stop_frequency_hz=stop_frequency_hz,
                        points_per_decade=points_per_decade,
                    )
                else:
                    text = generate_task7_transient_netlist(
                        config,
                        parameters,
                        **common,
                        transient_output_path=paths.runtime_ac,
                    )
                _write_netlist(paths.runtime_netlist, text)
                launches[kind] += 1
                process = run_ngspice(
                    paths.runtime_netlist,
                    executable=executable,
                    timeout_seconds=timeout_seconds,
                    log_path=paths.runtime_log,
                    preserve_runtime_paths=True,
                )
                processes[kind] = process
                if kind == "op":
                    operating_point = parse_task7_operating_point(
                        runtime_op, runtime_device
                    )
                    region = assess_task7_operating_regions(operating_point)
                elif kind == "ac":
                    ac_response = parse_ac_output(runtime_data)
                    stability = measure_task7_stability(ac_response)
                else:
                    transient_response = parse_task7_transient(runtime_data)
                    slew = measure_task7_slew(transient_response, config)
        except Exception as exc:
            # Each failure is isolated so the later high-fidelity analyses are
            # still launched; this is the Full-only policy, not a screening path.
            errors[kind] = f"{type(exc).__name__}: {exc}"
        finally:
            runtimes[kind] = monotonic() - analysis_started

    metrics: dict[str, float | None] = {
        "dc_gain_db": stability.dc_gain_db,
        "ugf_hz": stability.ugf_hz,
        "ugf_lower_bound_hz": stability.ugf_lower_bound_hz,
        "phase_margin_deg": stability.phase_margin_deg,
        "minus_3db_bandwidth_hz": (
            None if ac_response is None else optional_minus_3db_bandwidth(ac_response)
        ),
        "dc_power_w": None if operating_point is None else operating_point.dc_power_w,
        "supply_current_a": (
            None if operating_point is None else operating_point.supply_current_a
        ),
        "output_dc_voltage": (
            None if operating_point is None else operating_point.output_voltage_v
        ),
        "stage1_dc_voltage": (
            None if operating_point is None else operating_point.stage1_voltage_v
        ),
        "positive_slew_v_per_s": slew.positive_slew_v_per_s,
        "negative_slew_v_per_s": slew.negative_slew_v_per_s,
        "operating_region_valid": None if region is None else float(region.valid),
    }
    return Task7FullEvaluation(
        operating_point=operating_point,
        operating_region=region,
        ac_response=ac_response,
        stability=stability,
        transient_response=transient_response,
        slew=slew,
        metrics=metrics,
        processes=processes,
        errors=errors,
        cost=Task7AnalysisCost(
            candidate_evaluations=1,
            ngspice_process_calls=sum(launches.values()),
            op_calls=launches["op"],
            ac_calls=launches["ac"],
            transient_calls=launches["transient"],
            high_fidelity_analysis_calls=sum(launches.values()),
            op_runtime_seconds=runtimes["op"],
            ac_runtime_seconds=runtimes["ac"],
            transient_runtime_seconds=runtimes["transient"],
            wall_clock_seconds=monotonic() - started,
        ),
    )
