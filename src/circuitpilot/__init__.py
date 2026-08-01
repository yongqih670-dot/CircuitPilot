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
from circuitpilot.circuit_optimizer import (
    OptimizationEvaluation,
    OptimizationResult,
    evaluate_response_metric,
    metric_to_objective,
    plot_optimization_progress,
    run_circuit_optimization,
    save_optimization_history_csv,
    save_optimization_summary_json,
)
from circuitpilot.netlist import RCFilterConfig, write_rc_lowpass_netlist
from circuitpilot.netlist_generator import generate_netlist, write_netlist
from circuitpilot.optimization_config import (
    ObjectiveConfig,
    ObjectiveGoal,
    ObjectiveMetric,
    OptimizationConfig,
    OptimizerSettings,
    ParameterBounds,
    ParameterScale,
    load_optimization_config,
)
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
from circuitpilot.research_artifacts import (
    RESEARCH_MANIFEST_FILENAME,
    RESEARCH_MANIFEST_SCHEMA_VERSION,
    write_research_manifest,
)
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

__version__ = "0.5.0"

__all__ = [
    "ACAnalysisResult",
    "ACAnalysisConfig",
    "CircuitConfig",
    "CircuitType",
    "ExperimentComparison",
    "ExperimentRecord",
    "ExperimentRepository",
    "ObjectiveConfig",
    "ObjectiveGoal",
    "ObjectiveMetric",
    "OptimizationConfig",
    "OptimizationEvaluation",
    "OptimizationResult",
    "OptimizerSettings",
    "ParameterBounds",
    "ParameterScale",
    "RESEARCH_MANIFEST_FILENAME",
    "RESEARCH_MANIFEST_SCHEMA_VERSION",
    "RCHighPassConfig",
    "RCFilterConfig",
    "RCLowPassConfig",
    "SimulationResult",
    "SweepConfig",
    "SweepResult",
    "VoltageDividerConfig",
    "ParameterCombination",
    "calculate_relative_error",
    "evaluate_response_metric",
    "find_cutoff_frequency",
    "find_highpass_cutoff_frequency",
    "generate_netlist",
    "generate_parameter_combinations",
    "load_circuit_config",
    "load_optimization_config",
    "load_sweep_config",
    "parse_ac_output",
    "plot_optimization_progress",
    "run_ngspice",
    "resolve_ngspice_executable",
    "run_parameter_sweep",
    "run_circuit_optimization",
    "rank_solutions",
    "save_sweep_results_csv",
    "save_optimization_history_csv",
    "save_optimization_summary_json",
    "metric_to_objective",
    "write_rc_lowpass_netlist",
    "write_netlist",
    "write_research_manifest",
]
