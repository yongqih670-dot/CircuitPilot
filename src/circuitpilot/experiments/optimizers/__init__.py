"""Traditional optimizer adapters for CircuitPilot research baselines."""

from circuitpilot.experiments.optimizers.base import Optimizer, OptimizerFeedback
from circuitpilot.experiments.optimizers.bayesian import BayesianOptimizationOptimizer
from circuitpilot.experiments.optimizers.differential_evolution import DifferentialEvolutionOptimizer
from circuitpilot.experiments.optimizers.factory import create_optimizer
from circuitpilot.experiments.optimizers.random_search import RandomOptimizer
from circuitpilot.experiments.optimizers.tpe import TPEOptimizer

__all__ = [
    "BayesianOptimizationOptimizer",
    "DifferentialEvolutionOptimizer",
    "Optimizer",
    "OptimizerFeedback",
    "RandomOptimizer",
    "TPEOptimizer",
    "create_optimizer",
]
