"""Unified, fair, and reproducible research experiment infrastructure."""

from circuitpilot.experiments.budget import SimulationBudget
from circuitpilot.experiments.config import (
    ConstraintDefinition,
    ConstraintOperator,
    ExperimentConfig,
    NgspiceConfig,
    ObjectiveDefinition,
    ObjectiveType,
    ParameterType,
    SearchParameter,
    experiment_config_from_mapping,
    load_experiment_config,
    write_experiment_config,
)
from circuitpilot.experiments.seeding import (
    SeedContext,
    SeedRegistry,
    initialize_seeds,
)
from circuitpilot.experiments.objectives import (
    ObjectiveEvaluation,
    ObjectiveEvaluator,
)
from circuitpilot.experiments.optimizer import (
    Optimizer,
    OptimizerFeedback,
    RandomOptimizer,
    create_optimizer,
)
from circuitpilot.experiments.recorder import (
    EVALUATION_COLUMNS,
    EvaluationRecord,
    EvaluationRecorder,
)
from circuitpilot.experiments.runner import (
    ExperimentRunResult,
    ExperimentRunner,
    execute_experiment,
)

__all__ = [
    "ConstraintDefinition",
    "ConstraintOperator",
    "ExperimentConfig",
    "NgspiceConfig",
    "ObjectiveEvaluation",
    "ObjectiveEvaluator",
    "ObjectiveDefinition",
    "ObjectiveType",
    "ParameterType",
    "Optimizer",
    "OptimizerFeedback",
    "RandomOptimizer",
    "SearchParameter",
    "SeedContext",
    "SeedRegistry",
    "SimulationBudget",
    "EVALUATION_COLUMNS",
    "EvaluationRecord",
    "EvaluationRecorder",
    "ExperimentRunResult",
    "ExperimentRunner",
    "create_optimizer",
    "execute_experiment",
    "experiment_config_from_mapping",
    "initialize_seeds",
    "load_experiment_config",
    "write_experiment_config",
]
