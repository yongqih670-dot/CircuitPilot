"""Task 6 operating-point-only evidence and transparent physics rules."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import os
from pathlib import Path
from typing import Callable, Mapping

from circuitpilot.common_source import dc_supply_power
from circuitpilot.exceptions import NetlistError
from circuitpilot.parser import ACAnalysisResult, parse_ac_output
from circuitpilot.simulator import SimulationResult, run_ngspice
from circuitpilot.sky130_common_source import sky130_runtime_paths
from circuitpilot.sky130_differential_amplifier import (
    DEVICE_ROLES,
    DifferentialOperatingPoint,
    Sky130DifferentialAmplifierCircuitConfig,
    parse_differential_operating_point,
)


PHYSICS_RULES_VERSION = "task6_op_physics_rules_v1"
OP_FEEDBACK_SEMANTICS_VERSION = "task6_normalized_op_violation_feedback_v1"
OUTPUT_LOW_V = 0.25
OUTPUT_HIGH_V = 1.55
OFF_MARGIN_V = 1e-9
REJECTED_OBJECTIVE_BASE = 1000.0

VIOLATION_BITS = {
    "input_pair_off": 1,
    "input_pair_not_saturated": 2,
    "active_load_off": 4,
    "active_load_not_saturated": 8,
    "tail_off": 16,
    "tail_not_saturated": 32,
    "output_headroom_invalid": 64,
}


@dataclass(frozen=True, slots=True)
class PhysicsAssessment:
    """Transparent Task 6 classification derived only from real OP vectors."""

    physics_status: str
    violation_mask: int
    violation_count: int
    violation_types: tuple[str, ...]
    op_constraint_violation: float
    device_region_valid: Mapping[str, bool]


@dataclass(frozen=True, slots=True)
class OperatingPointOnlyResult:
    """Evidence from one successful explicit OP-only ngspice process."""

    operating_point: DifferentialOperatingPoint
    process: SimulationResult
    netlist_path: Path
    op_path: Path
    device_op_path: Path
    log_path: Path


@dataclass(frozen=True, slots=True)
class ACOnlyResult:
    """Evidence from one conditional combined differential/common AC process."""

    differential_response: ACAnalysisResult
    common_mode_response: ACAnalysisResult
    process: SimulationResult
    netlist_path: Path
    differential_path: Path
    common_mode_path: Path
    log_path: Path


def _safe_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    if '"' in normalized or "\n" in normalized or "\r" in normalized:
        raise NetlistError("ngspice paths cannot contain quotes or newlines")
    return normalized


def _device_line(
    name: str,
    nodes: str,
    device: str,
    width_um: float,
    length_um: float,
) -> str:
    return (
        f"X{name} {nodes} {device} "
        f"W={width_um:.12g} L={length_um:.12g}"
    )


def _device_vector(instance: str, device: str) -> str:
    internal = f"m.x{instance.lower()}.m{device}"
    return " ".join(
        f"@{internal}[{quantity}]"
        for quantity in ("vgs", "vds", "gm", "gds", "vth", "vdsat")
    )


def generate_task6_op_only_netlist(
    config: Sky130DifferentialAmplifierCircuitConfig,
    parameters: Mapping[str, float | int],
    *,
    invariant_path: str,
    nfet_corner_path: str,
    pfet_corner_path: str,
    op_output_path: str,
    device_op_output_path: str,
) -> str:
    """Generate the frozen Task 5 topology with only an explicit OP command."""
    expected = {
        "input_pair_width_m",
        "input_pair_length_m",
        "active_load_width_m",
        "active_load_length_m",
        "tail_width_m",
        "tail_length_m",
        "tail_bias_v",
    }
    if set(parameters) != expected:
        raise NetlistError("Task 6 OP-only parameters must match Task 5")
    values = {name: float(parameters[name]) for name in expected}
    if not all(isfinite(value) for value in values.values()):
        raise NetlistError("Task 6 OP-only candidate values must be finite")
    if any(values[name] <= 0 for name in expected if name != "tail_bias_v"):
        raise NetlistError("Task 6 transistor dimensions must be positive")
    if not 0 <= values["tail_bias_v"] <= config.supply_voltage_v:
        raise NetlistError("tail_bias_v must be between ground and VDD")

    paths = {
        name: _safe_path(path)
        for name, path in {
            "invariant": invariant_path,
            "nfet": nfet_corner_path,
            "pfet": pfet_corner_path,
            "op": op_output_path,
            "device": device_op_output_path,
        }.items()
    }
    iw = values["input_pair_width_m"] * 1e6
    il = values["input_pair_length_m"] * 1e6
    lw = values["active_load_width_m"] * 1e6
    ll = values["active_load_length_m"] * 1e6
    tw = values["tail_width_m"] * 1e6
    tl = values["tail_length_m"] * 1e6
    device_vectors = " ".join(
        (
            _device_vector("DM1", config.nfet_device_name),
            _device_vector("DM2", config.nfet_device_name),
            _device_vector("DL1", config.pfet_device_name),
            _device_vector("DL2", config.pfet_device_name),
            _device_vector("DTAIL", config.nfet_device_name),
        )
    )
    lines = [
        "* CircuitPilot Task 6 explicit OP-only pilot/stage",
        ".option scale=1u",
        ".param mc_mm_switch=0 mc_pr_switch=0",
        f'.include "{paths["invariant"]}"',
        f'.include "{paths["nfet"]}"',
        f'.include "{paths["pfet"]}"',
        f".temp {config.temperature_c:.12g}",
        f"VDD_D vdd_D 0 DC {config.supply_voltage_v:.12g}",
        f"VINP_D inp_D 0 DC {config.input_common_mode_v:.12g}",
        f"VINN_D inn_D 0 DC {config.input_common_mode_v:.12g}",
        f"VTAIL_D tail_bias_D 0 DC {values['tail_bias_v']:.12g}",
        _device_line(
            "DM1", "mirror_D inp_D tail_D 0",
            config.nfet_device_name, iw, il,
        ),
        _device_line(
            "DM2", "out_D inn_D tail_D 0",
            config.nfet_device_name, iw, il,
        ),
        _device_line(
            "DL1", "mirror_D mirror_D vdd_D vdd_D",
            config.pfet_device_name, lw, ll,
        ),
        _device_line(
            "DL2", "out_D mirror_D vdd_D vdd_D",
            config.pfet_device_name, lw, ll,
        ),
        _device_line(
            "DTAIL", "tail_D tail_bias_D tail_source_D 0",
            config.nfet_device_name, tw, tl,
        ),
        "VSENSE_D tail_source_D 0 0",
        f"CL_D out_D 0 {config.load_capacitance_f:.12g}",
        ".control",
        "set wr_singlescale",
        "set wr_vecnames",
        "op",
        f'wrdata {paths["op"]} v(vdd_D) v(inp_D) v(inn_D) v(out_D) '
        "v(tail_D) i(VDD_D) i(VSENSE_D)",
        f'wrdata {paths["device"]} {device_vectors}',
        "quit",
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


def run_task6_op_only(
    config: Sky130DifferentialAmplifierCircuitConfig,
    parameters: Mapping[str, float | int],
    evaluation_directory: Path,
    *,
    executable: str = "ngspice",
    timeout_seconds: float = 30.0,
    on_ngspice_launch: Callable[[], None] | None = None,
) -> OperatingPointOnlyResult:
    """Execute and parse one explicit OP-only process."""
    with sky130_runtime_paths(config.model, evaluation_directory) as paths:
        windows_runtime = os.name == "nt"
        runtime_op = Path(paths.runtime_op) if windows_runtime else paths.op_path
        runtime_device = (
            Path(paths.runtime_device) if windows_runtime else paths.device_path
        )
        for path in (runtime_op, runtime_device, paths.runtime_log):
            path.unlink(missing_ok=True)
        text = generate_task6_op_only_netlist(
            config,
            parameters,
            invariant_path=paths.runtime_invariant,
            nfet_corner_path=paths.runtime_corner,
            pfet_corner_path=paths.runtime_pfet_corner,
            op_output_path=paths.runtime_op,
            device_op_output_path=paths.runtime_device,
        )
        paths.runtime_netlist.write_text(text, encoding="utf-8")
        if on_ngspice_launch is not None:
            on_ngspice_launch()
        process = run_ngspice(
            paths.runtime_netlist,
            executable=executable,
            timeout_seconds=timeout_seconds,
            log_path=paths.runtime_log,
            preserve_runtime_paths=True,
        )
        operating_point = parse_differential_operating_point(
            runtime_op, runtime_device
        )
    return OperatingPointOnlyResult(
        operating_point=operating_point,
        process=process,
        netlist_path=paths.netlist_path,
        op_path=paths.op_path,
        device_op_path=paths.device_path,
        log_path=paths.log_path,
    )


def generate_task6_ac_only_netlist(
    config: Sky130DifferentialAmplifierCircuitConfig,
    parameters: Mapping[str, float | int],
    *,
    invariant_path: str,
    nfet_corner_path: str,
    pfet_corner_path: str,
    differential_ac_output_path: str,
    common_mode_ac_output_path: str,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
) -> str:
    """Generate unchanged Task 5 topology with only the combined dual AC."""
    expected = {
        "input_pair_width_m",
        "input_pair_length_m",
        "active_load_width_m",
        "active_load_length_m",
        "tail_width_m",
        "tail_length_m",
        "tail_bias_v",
    }
    if set(parameters) != expected:
        raise NetlistError("Task 6 AC-only parameters must match Task 5")
    values = {name: float(parameters[name]) for name in expected}
    if not all(isfinite(value) for value in values.values()):
        raise NetlistError("Task 6 AC-only candidate values must be finite")
    if any(values[name] <= 0 for name in expected if name != "tail_bias_v"):
        raise NetlistError("Task 6 transistor dimensions must be positive")
    if not 0 <= values["tail_bias_v"] <= config.supply_voltage_v:
        raise NetlistError("tail_bias_v must be between ground and VDD")
    if start_frequency_hz <= 0 or stop_frequency_hz <= start_frequency_hz:
        raise NetlistError("invalid fixed AC measurement window")
    if points_per_decade < 2:
        raise NetlistError("points_per_decade must be at least 2")
    paths = {
        name: _safe_path(path)
        for name, path in {
            "invariant": invariant_path,
            "nfet": nfet_corner_path,
            "pfet": pfet_corner_path,
            "differential": differential_ac_output_path,
            "common": common_mode_ac_output_path,
        }.items()
    }
    iw = values["input_pair_width_m"] * 1e6
    il = values["input_pair_length_m"] * 1e6
    lw = values["active_load_width_m"] * 1e6
    ll = values["active_load_length_m"] * 1e6
    tw = values["tail_width_m"] * 1e6
    tl = values["tail_length_m"] * 1e6

    def devices(suffix: str) -> list[str]:
        return [
            _device_line(
                f"{suffix}M1", f"mirror_{suffix} inp_{suffix} tail_{suffix} 0",
                config.nfet_device_name, iw, il,
            ),
            _device_line(
                f"{suffix}M2", f"out_{suffix} inn_{suffix} tail_{suffix} 0",
                config.nfet_device_name, iw, il,
            ),
            _device_line(
                f"{suffix}L1",
                f"mirror_{suffix} mirror_{suffix} vdd_{suffix} vdd_{suffix}",
                config.pfet_device_name, lw, ll,
            ),
            _device_line(
                f"{suffix}L2",
                f"out_{suffix} mirror_{suffix} vdd_{suffix} vdd_{suffix}",
                config.pfet_device_name, lw, ll,
            ),
            _device_line(
                f"{suffix}TAIL",
                f"tail_{suffix} tail_bias_{suffix} tail_source_{suffix} 0",
                config.nfet_device_name, tw, tl,
            ),
            f"VSENSE_{suffix} tail_source_{suffix} 0 0",
        ]

    lines = [
        "* CircuitPilot Task 6 conditional AC-only stage",
        ".option scale=1u",
        ".param mc_mm_switch=0 mc_pr_switch=0",
        f'.include "{paths["invariant"]}"',
        f'.include "{paths["nfet"]}"',
        f'.include "{paths["pfet"]}"',
        f".temp {config.temperature_c:.12g}",
        f"VDD_D vdd_D 0 DC {config.supply_voltage_v:.12g}",
        f"VINP_D inp_D 0 DC {config.input_common_mode_v:.12g} AC 0.5 0",
        f"VINN_D inn_D 0 DC {config.input_common_mode_v:.12g} AC 0.5 180",
        f"VTAIL_D tail_bias_D 0 DC {values['tail_bias_v']:.12g}",
        *devices("D"),
        f"CL_D out_D 0 {config.load_capacitance_f:.12g}",
        f"VDD_C vdd_C 0 DC {config.supply_voltage_v:.12g}",
        f"VINP_C inp_C 0 DC {config.input_common_mode_v:.12g} AC 1 0",
        f"VINN_C inn_C 0 DC {config.input_common_mode_v:.12g} AC 1 0",
        f"VTAIL_C tail_bias_C 0 DC {values['tail_bias_v']:.12g}",
        *devices("C"),
        f"CL_C out_C 0 {config.load_capacitance_f:.12g}",
        ".control",
        "set wr_singlescale",
        "set wr_vecnames",
        f"ac dec {points_per_decade} {start_frequency_hz:.12g} "
        f"{stop_frequency_hz:.12g}",
        f'wrdata {paths["differential"]} vdb(out_D) vp(out_D)',
        f'wrdata {paths["common"]} vdb(out_C) vp(out_C)',
        "quit",
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


def run_task6_ac_only(
    config: Sky130DifferentialAmplifierCircuitConfig,
    parameters: Mapping[str, float | int],
    evaluation_directory: Path,
    *,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
    executable: str = "ngspice",
    timeout_seconds: float = 30.0,
    on_ngspice_launch: Callable[[], None] | None = None,
) -> ACOnlyResult:
    """Execute one conditional process containing the two logical AC tests."""
    common_path = evaluation_directory.resolve() / "common_ac.dat"
    with sky130_runtime_paths(config.model, evaluation_directory) as paths:
        windows_runtime = os.name == "nt"
        runtime_differential = (
            Path(paths.runtime_ac) if windows_runtime else paths.ac_path
        )
        runtime_common = (
            Path(paths.runtime_ac).with_name(common_path.name)
            if windows_runtime
            else common_path
        )
        for path in (runtime_differential, runtime_common, paths.runtime_log):
            path.unlink(missing_ok=True)
        text = generate_task6_ac_only_netlist(
            config,
            parameters,
            invariant_path=paths.runtime_invariant,
            nfet_corner_path=paths.runtime_corner,
            pfet_corner_path=paths.runtime_pfet_corner,
            differential_ac_output_path=paths.runtime_ac,
            common_mode_ac_output_path=runtime_common.as_posix(),
            start_frequency_hz=start_frequency_hz,
            stop_frequency_hz=stop_frequency_hz,
            points_per_decade=points_per_decade,
        )
        paths.runtime_netlist.write_text(text, encoding="utf-8")
        if on_ngspice_launch is not None:
            on_ngspice_launch()
        process = run_ngspice(
            paths.runtime_netlist,
            executable=executable,
            timeout_seconds=timeout_seconds,
            log_path=paths.runtime_log,
            preserve_runtime_paths=True,
        )
        differential = parse_ac_output(runtime_differential)
        common = parse_ac_output(runtime_common)
    return ACOnlyResult(
        differential_response=differential,
        common_mode_response=common,
        process=process,
        netlist_path=paths.netlist_path,
        differential_path=paths.ac_path,
        common_mode_path=common_path,
        log_path=paths.log_path,
    )


def task6_operating_point_metrics(
    operating_point: DifferentialOperatingPoint,
) -> dict[str, float | None]:
    """Flatten exactly measured OP values while leaving every AC metric null."""
    assessment = classify_task6_physics(operating_point)
    flattened = {
        f"{role}_{quantity}": float(value)
        for role, quantities in operating_point.device_quantities.items()
        for quantity, value in quantities.items()
    }
    return {
        "differential_gain_db": None,
        "common_mode_gain_db": None,
        "cmrr_db": None,
        "cmrr_lower_bound_db": None,
        "bandwidth_hz": None,
        "bandwidth_lower_bound_hz": None,
        "dc_power_w": dc_supply_power(
            operating_point.supply_voltage_v,
            operating_point.supply_current_a,
        ),
        "output_dc_voltage": operating_point.output_voltage_v,
        "tail_current_a": operating_point.tail_current_a,
        "supply_current_a": operating_point.supply_current_a,
        "tail_node_voltage_v": operating_point.tail_node_voltage_v,
        "operating_region_valid": float(
            all(assessment.device_region_valid.values())
        ),
        **{
            f"{role}_operating_region_valid": float(valid)
            for role, valid in assessment.device_region_valid.items()
        },
        **flattened,
    }


def _device_terms(
    role: str, values: Mapping[str, float]
) -> tuple[float, float, float]:
    required = {"vgs", "vds", "vth"}
    if not required <= set(values):
        raise ValueError(f"missing operating-point values for {role}")
    raw = tuple(float(values[name]) for name in ("vgs", "vds", "vth"))
    if not all(isfinite(value) for value in raw):
        raise ValueError(f"non-finite operating-point values for {role}")
    vgs, vds, vth = raw
    if role.startswith("load_"):
        return abs(vgs) - abs(vth), abs(vds), abs(vth)
    return vgs - vth, vds, abs(vth)


def classify_task6_physics(
    operating_point: DifferentialOperatingPoint,
) -> PhysicsAssessment:
    """Classify all simultaneous OP violations and compute fixed feedback."""
    states: dict[str, tuple[bool, bool]] = {}
    device_violation_total = 0.0
    region_valid: dict[str, bool] = {}
    for role in DEVICE_ROLES:
        overdrive, drain_headroom, threshold = _device_terms(
            role, operating_point.device_quantities[role]
        )
        off = overdrive <= 0.0
        not_saturated = not off and drain_headroom < overdrive
        off_deficit = max(0.0, OFF_MARGIN_V - overdrive) / max(
            threshold, 1e-3
        )
        saturation_deficit = (
            0.0
            if off
            else max(0.0, overdrive - drain_headroom)
            / max(overdrive, 1e-3)
        )
        device_violation_total += off_deficit + saturation_deficit
        states[role] = (off, not_saturated)
        region_valid[role] = not off and not not_saturated

    violations: list[str] = []
    if any(states[role][0] for role in ("input_m1", "input_m2")):
        violations.append("input_pair_off")
    if any(states[role][1] for role in ("input_m1", "input_m2")):
        violations.append("input_pair_not_saturated")
    if any(states[role][0] for role in ("load_mirror", "load_output")):
        violations.append("active_load_off")
    if any(states[role][1] for role in ("load_mirror", "load_output")):
        violations.append("active_load_not_saturated")
    if states["tail"][0]:
        violations.append("tail_off")
    if states["tail"][1]:
        violations.append("tail_not_saturated")

    output = float(operating_point.output_voltage_v)
    if not isfinite(output):
        raise ValueError("non-finite Task 6 output operating point")
    output_deficit = (
        max(0.0, OUTPUT_LOW_V - output)
        + max(0.0, output - OUTPUT_HIGH_V)
    ) / (OUTPUT_HIGH_V - OUTPUT_LOW_V)
    if output < OUTPUT_LOW_V or output > OUTPUT_HIGH_V:
        violations.append("output_headroom_invalid")

    count = len(violations)
    mask = sum(VIOLATION_BITS[name] for name in violations)
    types = tuple(
        [*violations]
        + (["multiple_physics_violations"] if count > 1 else [])
    )
    op_violation = (device_violation_total + output_deficit) / 6.0
    if count > 0 and not op_violation > 0.0:
        raise ValueError("physics-invalid candidate must have positive OP violation")
    return PhysicsAssessment(
        physics_status="valid" if count == 0 else "invalid",
        violation_mask=mask,
        violation_count=count,
        violation_types=types,
        op_constraint_violation=op_violation,
        device_region_valid=region_valid,
    )


def rejected_policy_objective(op_constraint_violation: float) -> float:
    """Return the frozen bounded OP-rejection optimizer feedback."""
    value = float(op_constraint_violation)
    if not isfinite(value) or value <= 0.0:
        raise ValueError("OP-rejected feedback requires a positive finite violation")
    return REJECTED_OBJECTIVE_BASE + value / (1.0 + value)
