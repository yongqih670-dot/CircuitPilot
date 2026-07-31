"""CircuitPilot: small building blocks for ngspice-based simulation."""

from circuitpilot.analysis import find_cutoff_frequency, find_highpass_cutoff_frequency
from circuitpilot.circuit_config import (
    ACAnalysisConfig,
    CircuitConfig,
    CircuitType,
    RCHighPassConfig,
    RCLowPassConfig,
    VoltageDividerConfig,
    load_circuit_config,
)
from circuitpilot.netlist import RCFilterConfig, write_rc_lowpass_netlist
from circuitpilot.netlist_generator import generate_netlist, write_netlist
from circuitpilot.experiment_manager import (
    ExperimentComparison,
    ExperimentRecord,
    ExperimentRepository,
)
from circuitpilot.parameter_sweep import (
    SweepResult,
    calculate_relative_error,
    rank_solutions,
    run_parameter_sweep,
    save_sweep_results_csv,
)
from circuitpilot.parser import ACAnalysisResult, parse_ac_output
from circuitpilot.simulator import (
    SimulationResult,
    resolve_ngspice_executable,
    run_ngspice,
)
from circuitpilot.sweep_config import (
    ParameterCombination,
    SweepConfig,
    generate_parameter_combinations,
    load_sweep_config,
)

__version__ = "0.4.0"

__all__ = [
    "ACAnalysisResult",
    "ACAnalysisConfig",
    "CircuitConfig",
    "CircuitType",
    "ExperimentComparison",
    "ExperimentRecord",
    "ExperimentRepository",
    "RCHighPassConfig",
    "RCFilterConfig",
    "RCLowPassConfig",
    "SimulationResult",
    "SweepConfig",
    "SweepResult",
    "VoltageDividerConfig",
    "ParameterCombination",
    "calculate_relative_error",
    "find_cutoff_frequency",
    "find_highpass_cutoff_frequency",
    "generate_netlist",
    "generate_parameter_combinations",
    "load_circuit_config",
    "load_sweep_config",
    "parse_ac_output",
    "run_ngspice",
    "resolve_ngspice_executable",
    "run_parameter_sweep",
    "rank_solutions",
    "save_sweep_results_csv",
    "write_rc_lowpass_netlist",
    "write_netlist",
]
