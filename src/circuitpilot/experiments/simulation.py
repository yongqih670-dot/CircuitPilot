"""Common real-ngspice candidate simulation boundary for research experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol

from circuitpilot.circuit_config import ACAnalysisConfig, CircuitConfig, RCLowPassConfig
from circuitpilot.common_source import (
    OperatingPointResult,
    parse_operating_point,
    write_common_source_netlist,
)
from circuitpilot.experiments.config import ExperimentConfig
from circuitpilot.netlist_generator import write_netlist
from circuitpilot.parser import ACAnalysisResult, parse_ac_output
from circuitpilot.simulator import SimulationResult, run_ngspice


@dataclass(frozen=True, slots=True)
class CandidateSimulation:
    """Raw evidence produced by one successful real ngspice candidate run."""

    response: ACAnalysisResult
    process: SimulationResult
    netlist_path: Path
    data_path: Path
    log_path: Path
    operating_point: OperatingPointResult | None = None
    dc_data_path: Path | None = None
    device_op_data_path: Path | None = None


class CandidateSimulator(Protocol):
    """Dependency boundary used by the optimizer-independent runner."""

    def evaluate(
        self,
        parameters: Mapping[str, float | int],
        evaluation_directory: Path,
        on_ngspice_launch: Callable[[], None],
    ) -> CandidateSimulation:
        """Run at most one real simulator call for a validated candidate."""


class RCLowPassNgspiceSimulator:
    """Generate, run, and parse the already-audited RC low-pass template."""

    def __init__(self, config: ExperimentConfig) -> None:
        """Bind common AC settings and executable selection."""
        if config.circuit_name != "rc_lowpass":
            raise ValueError("RCLowPassNgspiceSimulator supports only rc_lowpass")
        self._config = config

    def evaluate(
        self,
        parameters: Mapping[str, float | int],
        evaluation_directory: Path,
        on_ngspice_launch: Callable[[], None],
    ) -> CandidateSimulation:
        """Execute exactly one ngspice AC analysis and return parsed evidence."""
        resistance = float(parameters["resistance"])
        capacitance = float(parameters["capacitance"])
        circuit = CircuitConfig(
            circuit=RCLowPassConfig(resistance, capacitance),
            analysis=ACAnalysisConfig(
                self._config.ngspice_config.start_frequency_hz,
                self._config.ngspice_config.stop_frequency_hz,
                self._config.ngspice_config.points_per_decade,
            ),
        )
        evaluation_directory.mkdir(parents=True, exist_ok=True)
        netlist_path = evaluation_directory / "rc_lowpass.cir"
        data_path = evaluation_directory / "ac_results.dat"
        log_path = evaluation_directory / "ngspice.log"
        data_path.unlink(missing_ok=True)
        write_netlist(netlist_path, data_path, circuit)
        on_ngspice_launch()
        process = run_ngspice(
            netlist_path,
            executable=self._config.ngspice_config.executable,
            timeout_seconds=self._config.timeout,
            log_path=log_path,
        )
        response = parse_ac_output(data_path)
        return CandidateSimulation(
            response=response,
            process=process,
            netlist_path=netlist_path,
            data_path=data_path,
            log_path=log_path,
        )


class CommonSourceNgspiceSimulator:
    """Run one real combined DC operating-point and AC common-source analysis."""

    def __init__(self, config: ExperimentConfig) -> None:
        """Bind a validated transistor model and fixed benchmark definition."""
        if config.circuit_name != "common_source" or config.circuit_config is None:
            raise ValueError("CommonSourceNgspiceSimulator requires common_source config")
        self._config = config

    def evaluate(
        self,
        parameters: Mapping[str, float | int],
        evaluation_directory: Path,
        on_ngspice_launch: Callable[[], None],
    ) -> CandidateSimulation:
        """Execute exactly one ngspice process containing `.op` and `.ac`."""
        evaluation_directory.mkdir(parents=True, exist_ok=True)
        netlist_path = evaluation_directory / "common_source.cir"
        ac_path = evaluation_directory / "ac_results.dat"
        dc_path = evaluation_directory / "dc_operating_point.dat"
        device_path = evaluation_directory / "mos_operating_point.dat"
        log_path = evaluation_directory / "ngspice.log"
        for path in (ac_path, dc_path, device_path, log_path):
            path.unlink(missing_ok=True)
        write_common_source_netlist(
            netlist_path,
            self._config.circuit_config,
            parameters,
            ac_output_path=ac_path,
            op_output_path=dc_path,
            device_op_output_path=device_path,
            start_frequency_hz=self._config.ngspice_config.start_frequency_hz,
            stop_frequency_hz=self._config.ngspice_config.stop_frequency_hz,
            points_per_decade=self._config.ngspice_config.points_per_decade,
        )
        on_ngspice_launch()
        process = run_ngspice(
            netlist_path,
            executable=self._config.ngspice_config.executable,
            timeout_seconds=self._config.timeout,
            log_path=log_path,
        )
        response = parse_ac_output(ac_path)
        operating_point = parse_operating_point(dc_path, device_path)
        return CandidateSimulation(
            response=response,
            process=process,
            netlist_path=netlist_path,
            data_path=ac_path,
            log_path=log_path,
            operating_point=operating_point,
            dc_data_path=dc_path,
            device_op_data_path=device_path if device_path.is_file() else None,
        )
