"""Common real-ngspice candidate simulation boundary for research experiments."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol

from circuitpilot.circuit_config import ACAnalysisConfig, CircuitConfig, RCLowPassConfig
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
