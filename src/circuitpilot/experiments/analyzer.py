"""Physical metric extraction from parsed simulator evidence only."""

from __future__ import annotations

from dataclasses import dataclass
from math import log10
from typing import Mapping, Protocol

from circuitpilot.analysis import find_cutoff_frequency
from circuitpilot.bandwidth import BandwidthStatus, measure_bandwidth
from circuitpilot.circuit_config import CircuitType
from circuitpilot.common_source import analyze_common_source
from circuitpilot.exceptions import AnalysisError
from circuitpilot.experiments.config import ExperimentConfig
from circuitpilot.experiments.simulation import CandidateSimulation
from circuitpilot.power_metrics import derived_rc_power
from circuitpilot.power_metrics import dc_supply_power
from circuitpilot.sky130_differential_amplifier import (
    CmrrStatus,
    DifferentialOperatingPoint,
    Sky130DifferentialAmplifierCircuitConfig,
    device_operating_region_valid,
    measure_cmrr,
)


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    """Physical metrics plus explicit Task 4 measurement semantics."""

    metrics: dict[str, float | None]
    measurement_status: str = "complete"
    bandwidth_status: str | None = None
    bandwidth_lower_bound_hz: float | None = None
    cmrr_status: str | None = None
    cmrr_lower_bound_db: float | None = None
    message: str | None = None


class CandidateAnalyzer(Protocol):
    """Analyzer dependency used by the single common experiment runner."""

    def extract(
        self,
        simulation: CandidateSimulation,
        parameters: Mapping[str, float | int],
    ) -> dict[str, float] | AnalysisOutcome:
        """Return physical metrics derived only from simulator evidence."""


def _interpolate_log_frequency(
    frequencies: tuple[float, ...],
    values: tuple[float, ...],
    frequency_hz: float,
) -> float:
    """Interpolate one response value on the AC logarithmic frequency axis."""
    if frequency_hz < frequencies[0] or frequency_hz > frequencies[-1]:
        raise AnalysisError(
            f"metric frequency {frequency_hz:g} Hz is outside simulated AC range"
        )
    if frequency_hz == frequencies[0]:
        return values[0]
    for index in range(1, len(frequencies)):
        if frequency_hz <= frequencies[index]:
            lower_frequency = frequencies[index - 1]
            upper_frequency = frequencies[index]
            if frequency_hz == upper_frequency:
                return values[index]
            fraction = (log10(frequency_hz) - log10(lower_frequency)) / (
                log10(upper_frequency) - log10(lower_frequency)
            )
            return values[index - 1] + fraction * (values[index] - values[index - 1])
    return values[-1]


class RCLowPassAnalyzer:
    """Extract requested RC metrics from parsed AC response arrays."""

    _BANDWIDTH_NAMES = {
        "bandwidth",
        "bandwidth_hz",
        "cutoff_frequency",
        "cutoff_frequency_hz",
    }
    _GAIN_NAMES = {"gain", "gain_db"}
    _PHASE_NAMES = {"phase", "phase_deg"}
    _POWER_NAMES = {"power", "derived_rc_power", "derived_rc_power_w"}

    def __init__(self, config: ExperimentConfig) -> None:
        """Collect metric frequencies and reject ambiguous duplicate requests."""
        self._config = config
        frequencies: dict[str, float | None] = {}
        for definition in (*config.objectives, *config.constraints):
            existing = frequencies.get(definition.metric)
            if definition.metric in frequencies and existing != definition.frequency_hz:
                raise ValueError(
                    f"metric '{definition.metric}' uses conflicting frequency_hz values"
                )
            frequencies[definition.metric] = definition.frequency_hz
        self._frequencies = frequencies

    def extract(
        self,
        simulation: CandidateSimulation,
        parameters: Mapping[str, float | int],
    ) -> dict[str, float]:
        """Compute only explicitly requested metrics plus the raw sample count."""
        response = simulation.response
        metrics: dict[str, float] = {"sample_count": float(len(response))}
        cutoff: float | None = None
        for name, frequency_hz in self._frequencies.items():
            if name in self._BANDWIDTH_NAMES:
                if cutoff is None:
                    cutoff = find_cutoff_frequency(
                        response.frequency_hz, response.gain_db
                    )
                metrics[name] = cutoff
                continue
            selected_frequency = frequency_hz or response.frequency_hz[0]
            gain = _interpolate_log_frequency(
                response.frequency_hz, response.gain_db, selected_frequency
            )
            if name in self._GAIN_NAMES:
                metrics[name] = gain
                continue
            phase = _interpolate_log_frequency(
                response.frequency_hz, response.phase_deg, selected_frequency
            )
            if name in self._PHASE_NAMES:
                metrics[name] = phase
                continue
            if name in self._POWER_NAMES:
                metrics[name] = derived_rc_power(
                    gain_db=gain,
                    phase_deg=phase,
                    resistance_ohm=float(parameters["resistance"]),
                    circuit_type=CircuitType.RC_LOWPASS,
                )
                continue
            raise AnalysisError(
                f"metric '{name}' is not available for the rc_lowpass research baseline"
            )
        return metrics


class CommonSourceAnalyzer:
    """Extract transistor metrics only from parsed ngspice `.op` and `.ac` data."""

    _SUPPORTED = {
        "gain_db",
        "low_frequency_gain_db",
        "peak_gain_db",
        "bandwidth_hz",
        "bandwidth_3db_hz",
        "dc_power_w",
        "dc_supply_power",
        "output_dc_voltage",
        "supply_current_a",
        "vgs",
        "vds",
        "gm",
        "gds",
        "vth",
        "vdsat",
    }

    def __init__(self, config: ExperimentConfig) -> None:
        """Reject requests for metrics that this physical analyzer cannot emit."""
        if config.circuit_name != "common_source":
            raise ValueError("CommonSourceAnalyzer requires common_source config")
        requested = {
            definition.metric for definition in (*config.objectives, *config.constraints)
        }
        unsupported = sorted(requested - self._SUPPORTED)
        if unsupported:
            raise ValueError(
                "unsupported common_source metric(s): " + ", ".join(unsupported)
            )
        self._requested = requested

    def extract(
        self,
        simulation: CandidateSimulation,
        parameters: Mapping[str, float | int],
    ) -> dict[str, float]:
        """Return requested physical metrics and available MOS OP quantities."""
        del parameters
        if simulation.operating_point is None:
            raise AnalysisError("common-source simulation has no parsed operating point")
        measured = analyze_common_source(
            simulation.response, simulation.operating_point
        ).to_dict()
        measured.update(simulation.operating_point.device_quantities)
        missing = sorted(self._requested - set(measured))
        if missing:
            raise AnalysisError(
                "requested MOS operating-point quantity is unsupported by this model/ngspice: "
                + ", ".join(missing)
            )
        return {
            **{name: measured[name] for name in self._requested},
            "sample_count": float(len(simulation.response)),
        }


class Sky130CommonSourceAnalyzer:
    """Extract truthful SKY130 metrics, including censored bandwidth evidence."""

    _SUPPORTED = {
        "gain_db",
        "peak_gain_db",
        "bandwidth_hz",
        "bandwidth_lower_bound_hz",
        "dc_power_w",
        "dc_supply_power",
        "output_dc_voltage",
        "supply_current_a",
        "operating_region_valid",
        "vgs",
        "vds",
        "gm",
        "gds",
        "vth",
        "vdsat",
    }

    def __init__(self, config: ExperimentConfig) -> None:
        if config.circuit_name != "sky130_common_source":
            raise ValueError(
                "Sky130CommonSourceAnalyzer requires sky130_common_source config"
            )
        requested = {
            definition.metric for definition in (*config.objectives, *config.constraints)
        }
        unsupported = sorted(requested - self._SUPPORTED)
        if unsupported:
            raise ValueError(
                "unsupported SKY130 common-source metric(s): " + ", ".join(unsupported)
            )
        self._requested = requested

    def extract(
        self,
        simulation: CandidateSimulation,
        parameters: Mapping[str, float | int],
    ) -> AnalysisOutcome:
        """Return metrics derived only from real AC and `.op` evidence."""
        del parameters
        operating_point = simulation.operating_point
        if operating_point is None:
            return AnalysisOutcome(
                {},
                measurement_status="analysis_error",
                bandwidth_status=BandwidthStatus.ANALYSIS_ERROR.value,
                message="SKY130 simulation has no parsed operating point",
            )
        response = simulation.response
        bandwidth = measure_bandwidth(response.frequency_hz, response.gain_db)
        if bandwidth.bandwidth_status in {
            BandwidthStatus.INVALID_RESPONSE,
            BandwidthStatus.ANALYSIS_ERROR,
        }:
            return AnalysisOutcome(
                {},
                measurement_status=bandwidth.measurement_status,
                bandwidth_status=bandwidth.bandwidth_status.value,
                message=bandwidth.message,
            )

        device = dict(operating_point.device_quantities)
        measured: dict[str, float | None] = {
            "gain_db": float(response.gain_db[0]),
            "peak_gain_db": max(float(value) for value in response.gain_db),
            "bandwidth_hz": bandwidth.bandwidth_hz,
            "bandwidth_lower_bound_hz": bandwidth.bandwidth_lower_bound_hz,
            "dc_power_w": dc_supply_power(
                operating_point.supply_voltage_v, operating_point.supply_current_a
            ),
            "dc_supply_power": dc_supply_power(
                operating_point.supply_voltage_v, operating_point.supply_current_a
            ),
            "output_dc_voltage": operating_point.output_voltage_v,
            "supply_current_a": operating_point.supply_current_a,
            "sample_count": float(len(response)),
            **device,
        }
        if {"vgs", "vds", "vth"} <= set(device):
            overdrive = device["vgs"] - device["vth"]
            measured["operating_region_valid"] = float(
                device["vgs"] > device["vth"] and device["vds"] >= overdrive
            )
        missing = sorted(
            name
            for name in self._requested
            if name not in measured
            or (
                measured[name] is None
                and not (
                    name == "bandwidth_hz"
                    and bandwidth.bandwidth_status is BandwidthStatus.RIGHT_CENSORED
                )
            )
        )
        if missing:
            return AnalysisOutcome(
                measured,
                measurement_status="analysis_error",
                bandwidth_status=bandwidth.bandwidth_status.value,
                bandwidth_lower_bound_hz=bandwidth.bandwidth_lower_bound_hz,
                message="requested SKY130 metric(s) unavailable: " + ", ".join(missing),
            )
        return AnalysisOutcome(
            measured,
            measurement_status=bandwidth.measurement_status,
            bandwidth_status=bandwidth.bandwidth_status.value,
            bandwidth_lower_bound_hz=bandwidth.bandwidth_lower_bound_hz,
            message=bandwidth.message,
        )


class Sky130DifferentialAmplifierAnalyzer:
    """Extract direct Ad/Acm, censored bandwidth, CMRR, power, and OP metrics."""

    _SUPPORTED = {
        "differential_gain_db",
        "common_mode_gain_db",
        "cmrr_db",
        "cmrr_lower_bound_db",
        "bandwidth_hz",
        "bandwidth_lower_bound_hz",
        "dc_power_w",
        "output_dc_voltage",
        "tail_current_a",
        "operating_region_valid",
    }

    def __init__(self, config: ExperimentConfig) -> None:
        if (
            config.circuit_name != "sky130_differential_amplifier"
            or not isinstance(
                config.circuit_config, Sky130DifferentialAmplifierCircuitConfig
            )
        ):
            raise ValueError(
                "Sky130DifferentialAmplifierAnalyzer requires Task 5 config"
            )
        requested = {
            definition.metric for definition in (*config.objectives, *config.constraints)
        }
        unsupported = sorted(requested - self._SUPPORTED)
        if unsupported:
            raise ValueError(
                "unsupported SKY130 differential metric(s): " + ", ".join(unsupported)
            )
        self._requested = requested
        self._circuit = config.circuit_config

    def extract(
        self,
        simulation: CandidateSimulation,
        parameters: Mapping[str, float | int],
    ) -> AnalysisOutcome:
        del parameters
        operating_point = simulation.operating_point
        common = simulation.common_mode_response
        if not isinstance(operating_point, DifferentialOperatingPoint):
            return AnalysisOutcome(
                {},
                measurement_status="analysis_error",
                bandwidth_status=BandwidthStatus.ANALYSIS_ERROR.value,
                cmrr_status=CmrrStatus.INVALID.value,
                message="Task 5 simulation has no parsed differential operating point",
            )
        if common is None or len(common) < 2 or len(simulation.response) < 2:
            return AnalysisOutcome(
                {},
                measurement_status="invalid_response",
                bandwidth_status=BandwidthStatus.INVALID_RESPONSE.value,
                cmrr_status=CmrrStatus.INVALID.value,
                message="differential/common-mode AC response is incomplete",
            )
        differential = simulation.response
        bandwidth = measure_bandwidth(
            differential.frequency_hz, differential.gain_db
        )
        if bandwidth.bandwidth_status in {
            BandwidthStatus.INVALID_RESPONSE,
            BandwidthStatus.ANALYSIS_ERROR,
        }:
            return AnalysisOutcome(
                {},
                measurement_status=bandwidth.measurement_status,
                bandwidth_status=bandwidth.bandwidth_status.value,
                cmrr_status=CmrrStatus.INVALID.value,
                message="invalid differential response: " + (bandwidth.message or ""),
            )
        differential_gain = float(differential.gain_db[0])
        common_mode_gain = float(common.gain_db[0])
        cmrr = measure_cmrr(
            differential_gain,
            common_mode_gain,
            common_mode_gain_floor_db=self._circuit.common_mode_gain_floor_db,
        )
        if cmrr.status is CmrrStatus.INVALID:
            return AnalysisOutcome(
                {},
                measurement_status="invalid_response",
                bandwidth_status=bandwidth.bandwidth_status.value,
                bandwidth_lower_bound_hz=bandwidth.bandwidth_lower_bound_hz,
                cmrr_status=cmrr.status.value,
                message=cmrr.message,
            )
        flattened_devices = {
            f"{role}_{quantity}": float(value)
            for role, quantities in operating_point.device_quantities.items()
            for quantity, value in quantities.items()
        }
        region_by_role = {
            role: device_operating_region_valid(role, quantities)
            for role, quantities in operating_point.device_quantities.items()
        }
        power = dc_supply_power(
            operating_point.supply_voltage_v, operating_point.supply_current_a
        )
        measured: dict[str, float | None] = {
            "differential_gain_db": differential_gain,
            "common_mode_gain_db": common_mode_gain,
            "cmrr_db": cmrr.cmrr_db,
            "cmrr_lower_bound_db": cmrr.lower_bound_db,
            "bandwidth_hz": bandwidth.bandwidth_hz,
            "bandwidth_lower_bound_hz": bandwidth.bandwidth_lower_bound_hz,
            "dc_power_w": power,
            "output_dc_voltage": operating_point.output_voltage_v,
            "tail_current_a": operating_point.tail_current_a,
            "supply_current_a": operating_point.supply_current_a,
            "tail_node_voltage_v": operating_point.tail_node_voltage_v,
            "operating_region_valid": float(all(region_by_role.values())),
            "differential_sample_count": float(len(differential)),
            "common_mode_sample_count": float(len(common)),
            "candidate_evaluations": 1.0,
            "ngspice_process_calls": float(simulation.ngspice_process_calls),
            "analysis_calls": float(simulation.analysis_calls),
            **{
                f"{role}_operating_region_valid": float(valid)
                for role, valid in region_by_role.items()
            },
            **flattened_devices,
        }
        missing = sorted(
            name
            for name in self._requested
            if name not in measured
            or (
                measured[name] is None
                and not (
                    name == "bandwidth_hz"
                    and bandwidth.bandwidth_status is BandwidthStatus.RIGHT_CENSORED
                )
                and not (
                    name == "cmrr_db"
                    and cmrr.status is CmrrStatus.LOWER_BOUND
                )
            )
        )
        if missing:
            return AnalysisOutcome(
                measured,
                measurement_status="analysis_error",
                bandwidth_status=bandwidth.bandwidth_status.value,
                bandwidth_lower_bound_hz=bandwidth.bandwidth_lower_bound_hz,
                cmrr_status=cmrr.status.value,
                cmrr_lower_bound_db=cmrr.lower_bound_db,
                message="requested Task 5 metric(s) unavailable: " + ", ".join(missing),
            )
        return AnalysisOutcome(
            measured,
            measurement_status="complete",
            bandwidth_status=bandwidth.bandwidth_status.value,
            bandwidth_lower_bound_hz=bandwidth.bandwidth_lower_bound_hz,
            cmrr_status=cmrr.status.value,
            cmrr_lower_bound_db=cmrr.lower_bound_db,
            message=cmrr.message or bandwidth.message,
        )
