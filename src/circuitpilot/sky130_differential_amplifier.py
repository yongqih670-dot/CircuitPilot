"""Frozen SKY130 five-transistor differential-amplifier benchmark semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from pathlib import Path
import re
from typing import Any, Mapping

from circuitpilot.bandwidth import BANDWIDTH_SEMANTICS_VERSION
from circuitpilot.exceptions import ConfigError, NetlistError, ParseError
from circuitpilot.sky130_common_source import CENSORING_POLICY
from circuitpilot.sky130_model import (
    SKY130_DEVICE_NAME,
    SKY130_PFET_DEVICE_NAME,
    Sky130ModelConfig,
    sky130_model_from_mapping,
)


SKY130_DIFFERENTIAL_PARAMETER_NAMES = {
    "input_pair_width_m",
    "input_pair_length_m",
    "active_load_width_m",
    "active_load_length_m",
    "tail_width_m",
    "tail_length_m",
    "tail_bias_v",
}
TOPOLOGY_VERSION = "sky130_five_transistor_single_ended_ota_v1"
DEVICE_ROLE_MAPPING_VERSION = "matched_role_shared_sizing_v1"
DIFFERENTIAL_TESTBENCH_VERSION = "opposed_half_volt_sources_unit_differential_v1"
COMMON_MODE_TESTBENCH_VERSION = "equal_unit_sources_direct_common_mode_v1"
CMRR_SEMANTICS_VERSION = "direct_ad_acm_floor_lower_bound_v1"
SIMULATION_COST_SEMANTICS = "candidate_primary_one_process_op_plus_dual_testbench_ac_v1"
DIFFICULTY_PROTOCOL_VERSION = "task5_sky130_differential_difficulty_v1"

DEVICE_ROLES = (
    "input_m1",
    "input_m2",
    "load_mirror",
    "load_output",
    "tail",
)
DEVICE_ROLE_MAPPING = {
    "input_m1": {
        "device": SKY130_DEVICE_NAME,
        "size_role": "input_pair",
        "nodes": ("mirror", "vinp", "tail", "gnd"),
    },
    "input_m2": {
        "device": SKY130_DEVICE_NAME,
        "size_role": "input_pair",
        "nodes": ("vout", "vinn", "tail", "gnd"),
    },
    "load_mirror": {
        "device": SKY130_PFET_DEVICE_NAME,
        "size_role": "active_load",
        "nodes": ("mirror", "mirror", "vdd", "vdd"),
    },
    "load_output": {
        "device": SKY130_PFET_DEVICE_NAME,
        "size_role": "active_load",
        "nodes": ("vout", "mirror", "vdd", "vdd"),
    },
    "tail": {
        "device": SKY130_DEVICE_NAME,
        "size_role": "tail",
        "nodes": ("tail", "tail_bias", "gnd", "gnd"),
    },
}


@dataclass(frozen=True, slots=True)
class Sky130DifferentialAmplifierCircuitConfig:
    """Every fixed electrical, topology, measurement, and cost semantic."""

    supply_voltage_v: float
    input_common_mode_v: float
    load_capacitance_f: float
    temperature_c: float
    common_mode_gain_floor_db: float
    model: Sky130ModelConfig
    nfet_device_name: str = SKY130_DEVICE_NAME
    pfet_device_name: str = SKY130_PFET_DEVICE_NAME
    topology_version: str = TOPOLOGY_VERSION
    device_role_mapping_version: str = DEVICE_ROLE_MAPPING_VERSION
    differential_testbench_version: str = DIFFERENTIAL_TESTBENCH_VERSION
    common_mode_testbench_version: str = COMMON_MODE_TESTBENCH_VERSION
    cmrr_semantics_version: str = CMRR_SEMANTICS_VERSION
    bandwidth_semantics_version: str = BANDWIDTH_SEMANTICS_VERSION
    censoring_policy: str = CENSORING_POLICY
    simulation_cost_semantics: str = SIMULATION_COST_SEMANTICS
    difficulty_protocol_version: str = DIFFICULTY_PROTOCOL_VERSION

    def __post_init__(self) -> None:
        for name, value in (
            ("supply_voltage_v", self.supply_voltage_v),
            ("input_common_mode_v", self.input_common_mode_v),
            ("load_capacitance_f", self.load_capacitance_f),
            ("temperature_c", self.temperature_c),
            ("common_mode_gain_floor_db", self.common_mode_gain_floor_db),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"circuit_config.{name} must be numeric")
            if not isfinite(float(value)):
                raise ValueError(f"circuit_config.{name} must be finite")
        if not 0 < self.supply_voltage_v <= 1.8:
            raise ValueError("SKY130 01v8 differential benchmark supply must be in (0, 1.8]")
        if not 0 < self.input_common_mode_v < self.supply_voltage_v:
            raise ValueError("input_common_mode_v must be inside the supply rails")
        if self.load_capacitance_f <= 0:
            raise ValueError("load_capacitance_f must be positive")
        if self.common_mode_gain_floor_db >= 0:
            raise ValueError("common_mode_gain_floor_db must be negative")
        if not isinstance(self.model, Sky130ModelConfig):
            raise ValueError("sky130_model must be a Sky130ModelConfig")
        expected = {
            "nfet_device_name": SKY130_DEVICE_NAME,
            "pfet_device_name": SKY130_PFET_DEVICE_NAME,
            "topology_version": TOPOLOGY_VERSION,
            "device_role_mapping_version": DEVICE_ROLE_MAPPING_VERSION,
            "differential_testbench_version": DIFFERENTIAL_TESTBENCH_VERSION,
            "common_mode_testbench_version": COMMON_MODE_TESTBENCH_VERSION,
            "cmrr_semantics_version": CMRR_SEMANTICS_VERSION,
            "bandwidth_semantics_version": BANDWIDTH_SEMANTICS_VERSION,
            "censoring_policy": CENSORING_POLICY,
            "simulation_cost_semantics": SIMULATION_COST_SEMANTICS,
            "difficulty_protocol_version": DIFFICULTY_PROTOCOL_VERSION,
        }
        for name, required in expected.items():
            if getattr(self, name) != required:
                raise ValueError(f"unsupported Task 5 {name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "supply_voltage_v": self.supply_voltage_v,
            "input_common_mode_v": self.input_common_mode_v,
            "load_capacitance_f": self.load_capacitance_f,
            "temperature_c": self.temperature_c,
            "common_mode_gain_floor_db": self.common_mode_gain_floor_db,
            "nfet_device_name": self.nfet_device_name,
            "pfet_device_name": self.pfet_device_name,
            "topology_version": self.topology_version,
            "topology_definition": {
                "kind": "five_transistor_single_ended",
                "input_pair": "NMOS",
                "active_load": "1:1 PMOS current mirror",
                "tail_source": "NMOS voltage-biased current source",
            },
            "device_role_mapping_version": self.device_role_mapping_version,
            "device_role_mapping": DEVICE_ROLE_MAPPING,
            "differential_testbench_version": self.differential_testbench_version,
            "differential_testbench_definition": {
                "vinp_ac_magnitude": 0.5,
                "vinp_ac_phase_deg": 0.0,
                "vinn_ac_magnitude": 0.5,
                "vinn_ac_phase_deg": 180.0,
                "differential_input_magnitude": 1.0,
            },
            "common_mode_testbench_version": self.common_mode_testbench_version,
            "common_mode_testbench_definition": {
                "vinp_ac_magnitude": 1.0,
                "vinp_ac_phase_deg": 0.0,
                "vinn_ac_magnitude": 1.0,
                "vinn_ac_phase_deg": 0.0,
                "common_mode_input_magnitude": 1.0,
            },
            "cmrr_semantics_version": self.cmrr_semantics_version,
            "bandwidth_semantics_version": self.bandwidth_semantics_version,
            "censoring_policy": self.censoring_policy,
            "simulation_cost_semantics": self.simulation_cost_semantics,
            "simulation_cost_definition": {
                "primary_budget_unit": "candidate_evaluation",
                "ngspice_process_calls_per_candidate": 1,
                "physical_analysis_calls_per_candidate": 2,
                "logical_ac_testbenches_per_candidate": 2,
            },
            "difficulty_protocol_version": self.difficulty_protocol_version,
            "sky130_model": self.model.to_dict(),
        }


def sky130_differential_config_from_mapping(
    value: Mapping[str, Any], *, base_directory: Path | None = None
) -> Sky130DifferentialAmplifierCircuitConfig:
    if not isinstance(value, Mapping):
        raise ConfigError("circuit_config must be a YAML mapping")
    required = {
        "supply_voltage_v",
        "input_common_mode_v",
        "load_capacitance_f",
        "temperature_c",
        "common_mode_gain_floor_db",
        "nfet_device_name",
        "pfet_device_name",
        "topology_version",
        "device_role_mapping_version",
        "differential_testbench_version",
        "common_mode_testbench_version",
        "cmrr_semantics_version",
        "bandwidth_semantics_version",
        "censoring_policy",
        "simulation_cost_semantics",
        "difficulty_protocol_version",
        "sky130_model",
    }
    missing = sorted(required - set(value))
    unknown = sorted(set(value) - required)
    if missing:
        raise ConfigError(f"circuit_config is missing required field(s): {', '.join(missing)}")
    if unknown:
        raise ConfigError(f"circuit_config contains unknown field(s): {', '.join(unknown)}")
    try:
        return Sky130DifferentialAmplifierCircuitConfig(
            supply_voltage_v=float(value["supply_voltage_v"]),
            input_common_mode_v=float(value["input_common_mode_v"]),
            load_capacitance_f=float(value["load_capacitance_f"]),
            temperature_c=float(value["temperature_c"]),
            common_mode_gain_floor_db=float(value["common_mode_gain_floor_db"]),
            model=sky130_model_from_mapping(
                value["sky130_model"], base_directory=base_directory
            ),
            nfet_device_name=value["nfet_device_name"],
            pfet_device_name=value["pfet_device_name"],
            topology_version=value["topology_version"],
            device_role_mapping_version=value["device_role_mapping_version"],
            differential_testbench_version=value["differential_testbench_version"],
            common_mode_testbench_version=value["common_mode_testbench_version"],
            cmrr_semantics_version=value["cmrr_semantics_version"],
            bandwidth_semantics_version=value["bandwidth_semantics_version"],
            censoring_policy=value["censoring_policy"],
            simulation_cost_semantics=value["simulation_cost_semantics"],
            difficulty_protocol_version=value["difficulty_protocol_version"],
        )
    except (TypeError, ValueError) as exc:
        raise ConfigError(str(exc)) from exc


def _safe_spice_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    if '"' in normalized or "\n" in normalized or "\r" in normalized:
        raise NetlistError("ngspice paths cannot contain quotes or newlines")
    return normalized


def _device_lines(
    suffix: str,
    config: Sky130DifferentialAmplifierCircuitConfig,
    *,
    input_w_um: float,
    input_l_um: float,
    load_w_um: float,
    load_l_um: float,
    tail_w_um: float,
    tail_l_um: float,
) -> tuple[str, ...]:
    return (
        f"X{suffix}M1 mirror_{suffix} inp_{suffix} tail_{suffix} 0 "
        f"{config.nfet_device_name} W={input_w_um:.12g} L={input_l_um:.12g}",
        f"X{suffix}M2 out_{suffix} inn_{suffix} tail_{suffix} 0 "
        f"{config.nfet_device_name} W={input_w_um:.12g} L={input_l_um:.12g}",
        f"X{suffix}L1 mirror_{suffix} mirror_{suffix} vdd_{suffix} vdd_{suffix} "
        f"{config.pfet_device_name} W={load_w_um:.12g} L={load_l_um:.12g}",
        f"X{suffix}L2 out_{suffix} mirror_{suffix} vdd_{suffix} vdd_{suffix} "
        f"{config.pfet_device_name} W={load_w_um:.12g} L={load_l_um:.12g}",
        f"X{suffix}TAIL tail_{suffix} tail_bias_{suffix} tail_source_{suffix} 0 "
        f"{config.nfet_device_name} W={tail_w_um:.12g} L={tail_l_um:.12g}",
        f"VSENSE_{suffix} tail_source_{suffix} 0 0",
    )


def _device_vector(instance: str, device: str) -> str:
    internal = f"m.x{instance.lower()}.m{device}"
    return " ".join(
        f"@{internal}[{quantity}]"
        for quantity in ("vgs", "vds", "gm", "gds", "vth", "vdsat")
    )


def generate_sky130_differential_amplifier_netlist(
    config: Sky130DifferentialAmplifierCircuitConfig,
    parameters: Mapping[str, float | int],
    *,
    invariant_path: str,
    nfet_corner_path: str,
    pfet_corner_path: str,
    differential_ac_output_path: str,
    common_mode_ac_output_path: str,
    op_output_path: str,
    device_op_output_path: str,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
) -> str:
    """Generate isolated differential/common-mode copies in one real process."""
    if set(parameters) != SKY130_DIFFERENTIAL_PARAMETER_NAMES:
        raise NetlistError(
            "SKY130 differential parameters must match the seven frozen role variables"
        )
    values = {name: float(parameters[name]) for name in SKY130_DIFFERENTIAL_PARAMETER_NAMES}
    if not all(isfinite(value) for value in values.values()):
        raise NetlistError("SKY130 differential candidate values must be finite")
    for name in (
        "input_pair_width_m",
        "input_pair_length_m",
        "active_load_width_m",
        "active_load_length_m",
        "tail_width_m",
        "tail_length_m",
    ):
        if values[name] <= 0:
            raise NetlistError(f"{name} must be positive")
    if not 0 <= values["tail_bias_v"] <= config.supply_voltage_v:
        raise NetlistError("tail_bias_v must be between ground and VDD")
    if start_frequency_hz <= 0 or stop_frequency_hz <= start_frequency_hz:
        raise NetlistError("invalid fixed AC measurement window")
    if points_per_decade < 2:
        raise NetlistError("points_per_decade must be at least 2")
    paths = {
        name: _safe_spice_path(path)
        for name, path in {
            "invariant": invariant_path,
            "nfet": nfet_corner_path,
            "pfet": pfet_corner_path,
            "diff": differential_ac_output_path,
            "common": common_mode_ac_output_path,
            "op": op_output_path,
            "device": device_op_output_path,
        }.items()
    }
    sizes = {
        "input_w_um": values["input_pair_width_m"] * 1e6,
        "input_l_um": values["input_pair_length_m"] * 1e6,
        "load_w_um": values["active_load_width_m"] * 1e6,
        "load_l_um": values["active_load_length_m"] * 1e6,
        "tail_w_um": values["tail_width_m"] * 1e6,
        "tail_l_um": values["tail_length_m"] * 1e6,
    }
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
        "* CircuitPilot Task 5 SKY130 differential-amplifier benchmark",
        ".option scale=1u",
        ".param mc_mm_switch=0 mc_pr_switch=0",
        f'.include "{paths["invariant"]}"',
        f'.include "{paths["nfet"]}"',
        f'.include "{paths["pfet"]}"',
        f".temp {config.temperature_c:.12g}",
        "* Differential-mode testbench: |VINP-VINN| = 1 V AC",
        f"VDD_D vdd_D 0 DC {config.supply_voltage_v:.12g}",
        f"VINP_D inp_D 0 DC {config.input_common_mode_v:.12g} AC 0.5 0",
        f"VINN_D inn_D 0 DC {config.input_common_mode_v:.12g} AC 0.5 180",
        f"VTAIL_D tail_bias_D 0 DC {values['tail_bias_v']:.12g}",
        *_device_lines("D", config, **sizes),
        f"CL_D out_D 0 {config.load_capacitance_f:.12g}",
        "* Common-mode testbench: VINP = VINN = 1 V AC",
        f"VDD_C vdd_C 0 DC {config.supply_voltage_v:.12g}",
        f"VINP_C inp_C 0 DC {config.input_common_mode_v:.12g} AC 1 0",
        f"VINN_C inn_C 0 DC {config.input_common_mode_v:.12g} AC 1 0",
        f"VTAIL_C tail_bias_C 0 DC {values['tail_bias_v']:.12g}",
        *_device_lines("C", config, **sizes),
        f"CL_C out_C 0 {config.load_capacitance_f:.12g}",
        ".control",
        "set wr_singlescale",
        "set wr_vecnames",
        "op",
        f'wrdata {paths["op"]} v(vdd_D) v(inp_D) v(inn_D) v(out_D) '
        "v(tail_D) i(VDD_D) i(VSENSE_D)",
        f'wrdata {paths["device"]} {device_vectors}',
        f"ac dec {points_per_decade} {start_frequency_hz:.12g} {stop_frequency_hz:.12g}",
        f'wrdata {paths["diff"]} vdb(out_D) vp(out_D)',
        f'wrdata {paths["common"]} vdb(out_C) vp(out_C)',
        "quit",
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


_SEPARATOR = re.compile(r"[\s,]+")


def _numeric_tail(path: str | Path, count: int) -> tuple[float, ...]:
    source = Path(path).resolve()
    try:
        lines = source.read_text(encoding="utf-8", errors="strict").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ParseError(f"failed to read operating-point output '{source}': {exc}") from exc
    rows: list[list[float]] = []
    for line_number, raw in enumerate(lines, start=1):
        text = raw.strip()
        if not text or text.startswith(("#", "*")):
            continue
        tokens = [token for token in _SEPARATOR.split(text) if token]
        try:
            values = [float(token.replace("D", "E").replace("d", "e")) for token in tokens]
        except ValueError:
            if not rows:
                continue
            raise ParseError(f"invalid operating-point data at line {line_number}") from None
        if not all(isfinite(value) for value in values):
            raise ParseError(f"non-finite operating-point value at line {line_number}")
        rows.append(values)
    if not rows or len(rows[-1]) < count:
        found = 0 if not rows else len(rows[-1])
        raise ParseError(f"operating-point output requires {count} values, found {found}")
    return tuple(rows[-1][-count:])


@dataclass(frozen=True, slots=True)
class DifferentialOperatingPoint:
    supply_voltage_v: float
    input_positive_voltage_v: float
    input_negative_voltage_v: float
    output_voltage_v: float
    tail_node_voltage_v: float
    supply_current_a: float
    tail_current_a: float
    device_quantities: Mapping[str, Mapping[str, float]]


def parse_differential_operating_point(
    op_output_path: str | Path, device_op_output_path: str | Path
) -> DifferentialOperatingPoint:
    required = _numeric_tail(op_output_path, 7)
    quantities = ("vgs", "vds", "gm", "gds", "vth", "vdsat")
    raw_devices = _numeric_tail(device_op_output_path, len(DEVICE_ROLES) * len(quantities))
    devices = {
        role: dict(zip(quantities, raw_devices[index * 6 : (index + 1) * 6]))
        for index, role in enumerate(DEVICE_ROLES)
    }
    return DifferentialOperatingPoint(
        supply_voltage_v=required[0],
        input_positive_voltage_v=required[1],
        input_negative_voltage_v=required[2],
        output_voltage_v=required[3],
        tail_node_voltage_v=required[4],
        supply_current_a=required[5],
        tail_current_a=abs(required[6]),
        device_quantities=devices,
    )


class CmrrStatus(str, Enum):
    MEASURED = "measured"
    LOWER_BOUND = "lower_bound"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class CmrrMeasurement:
    status: CmrrStatus
    cmrr_db: float | None
    lower_bound_db: float | None
    message: str | None = None


def measure_cmrr(
    differential_gain_db: float,
    common_mode_gain_db: float,
    *,
    common_mode_gain_floor_db: float,
) -> CmrrMeasurement:
    """Measure CMRR directly in dB, or expose a conservative lower bound."""
    values = (differential_gain_db, common_mode_gain_db, common_mode_gain_floor_db)
    if not all(isfinite(float(value)) for value in values):
        return CmrrMeasurement(CmrrStatus.INVALID, None, None, "non-finite gain")
    if common_mode_gain_floor_db >= 0:
        return CmrrMeasurement(CmrrStatus.INVALID, None, None, "invalid CMRR floor")
    if common_mode_gain_db <= common_mode_gain_floor_db:
        lower = differential_gain_db - common_mode_gain_floor_db
        return CmrrMeasurement(
            CmrrStatus.LOWER_BOUND,
            None,
            lower,
            "common-mode response is at or below the frozen reliable floor",
        )
    return CmrrMeasurement(
        CmrrStatus.MEASURED,
        differential_gain_db - common_mode_gain_db,
        None,
    )


def device_operating_region_valid(role: str, values: Mapping[str, float]) -> bool:
    """Apply explicit voltage inequalities; no simulator region enum is used."""
    if not {"vgs", "vds", "vth"} <= set(values):
        return False
    vgs = float(values["vgs"])
    vds = float(values["vds"])
    vth = float(values["vth"])
    if role.startswith("load_"):
        vsg = abs(vgs)
        vsd = abs(vds)
        threshold = abs(vth)
        return vsg > threshold and vsd >= vsg - threshold
    return vgs > vth and vds >= vgs - vth
