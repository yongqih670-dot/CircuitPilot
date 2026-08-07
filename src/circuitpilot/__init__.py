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
from circuitpilot.environment_fingerprint import RESEARCH_BASELINE_VERSION
from circuitpilot.parameter_sweep import (
    SweepResult,
    calculate_relative_error,
    rank_solutions,
    run_parameter_sweep,
    save_sweep_results_csv,
)
from circuitpilot.parser import ACAnalysisResult, parse_ac_output
from circuitpilot.power_metrics import (
    DC_SUPPLY_POWER_METRIC,
    DERIVED_RC_POWER_METRIC,
    dc_supply_power,
    derived_rc_power,
)
from circuitpilot.research_artifacts import (
    RESEARCH_MANIFEST_FILENAME,
    RESEARCH_MANIFEST_SCHEMA_VERSION,
    write_research_manifest,
)
from circuitpilot.run_directory import (
    RUN_CONTEXT_FILENAME,
    ResearchRunDirectory,
    generate_run_id,
    prepare_research_run_directory,
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
    "DC_SUPPLY_POWER_METRIC",
    "DERIVED_RC_POWER_METRIC",
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
    "RESEARCH_BASELINE_VERSION",
    "RUN_CONTEXT_FILENAME",
    "RCHighPassConfig",
    "RCFilterConfig",
    "RCLowPassConfig",
    "ResearchRunDirectory",
    "SimulationResult",
    "SweepConfig",
    "SweepResult",
    "VoltageDividerConfig",
    "ParameterCombination",
    "calculate_relative_error",
    "dc_supply_power",
    "derived_rc_power",
    "evaluate_response_metric",
    "find_cutoff_frequency",
    "find_highpass_cutoff_frequency",
    "generate_netlist",
    "generate_run_id",
    "generate_parameter_combinations",
    "load_circuit_config",
    "load_optimization_config",
    "load_sweep_config",
    "parse_ac_output",
    "plot_optimization_progress",
    "prepare_research_run_directory",
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
