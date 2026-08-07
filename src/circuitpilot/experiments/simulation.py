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
from circuitpilot.sky130_common_source import (
    Sky130CommonSourceCircuitConfig,
    generate_sky130_common_source_netlist,
    sky130_runtime_paths,
)


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


class Sky130CommonSourceNgspiceSimulator:
    """Run the independent, content-locked SKY130 Task 4 benchmark."""

    def __init__(self, config: ExperimentConfig) -> None:
        if (
            config.circuit_name != "sky130_common_source"
            or not isinstance(config.circuit_config, Sky130CommonSourceCircuitConfig)
        ):
            raise ValueError(
                "Sky130CommonSourceNgspiceSimulator requires SKY130 circuit config"
            )
        self._config = config

    def evaluate(
        self,
        parameters: Mapping[str, float | int],
        evaluation_directory: Path,
        on_ngspice_launch: Callable[[], None],
    ) -> CandidateSimulation:
        """Execute exactly one ngspice process containing real `.op` and `.ac`."""
        circuit = self._config.circuit_config
        assert isinstance(circuit, Sky130CommonSourceCircuitConfig)
        with sky130_runtime_paths(circuit.model, evaluation_directory) as paths:
            for path in (
                paths.ac_path,
                paths.op_path,
                paths.device_path,
                paths.log_path,
            ):
                path.unlink(missing_ok=True)
            text = generate_sky130_common_source_netlist(
                circuit,
                parameters,
                invariant_path=paths.runtime_invariant,
                corner_path=paths.runtime_corner,
                ac_output_path=paths.runtime_ac,
                op_output_path=paths.runtime_op,
                device_op_output_path=paths.runtime_device,
                start_frequency_hz=self._config.ngspice_config.start_frequency_hz,
                stop_frequency_hz=self._config.ngspice_config.stop_frequency_hz,
                points_per_decade=self._config.ngspice_config.points_per_decade,
            )
            try:
                paths.netlist_path.write_text(text, encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                from circuitpilot.exceptions import NetlistError

                raise NetlistError(
                    f"failed to write SKY130 netlist '{paths.netlist_path}': {exc}"
                ) from exc
            on_ngspice_launch()
            process = run_ngspice(
                paths.runtime_netlist,
                executable=self._config.ngspice_config.executable,
                timeout_seconds=self._config.timeout,
                log_path=paths.runtime_log,
                preserve_runtime_paths=True,
            )
            response = parse_ac_output(paths.ac_path)
            operating_point = parse_operating_point(
                paths.op_path, paths.device_path
            )
        return CandidateSimulation(
            response=response,
            process=process,
            netlist_path=paths.netlist_path,
            data_path=paths.ac_path,
            log_path=paths.log_path,
            operating_point=operating_point,
            dc_data_path=paths.op_path,
            device_op_data_path=paths.device_path,
        )
