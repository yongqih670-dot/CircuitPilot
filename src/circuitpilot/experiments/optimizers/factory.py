"""Single optimizer factory used by the shared ExperimentRunner."""

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.config import ExperimentConfig
from circuitpilot.experiments.optimizers.base import Optimizer
from circuitpilot.experiments.optimizers.bayesian import BayesianOptimizationOptimizer
from circuitpilot.experiments.optimizers.differential_evolution import DifferentialEvolutionOptimizer
from circuitpilot.experiments.optimizers.random_search import RandomOptimizer
from circuitpilot.experiments.optimizers.tpe import TPEOptimizer
from circuitpilot.experiments.seeding import SeedContext


def create_optimizer(config: ExperimentConfig, seeds: SeedContext) -> Optimizer:
    """Construct an adapter without introducing optimizer-specific run loops."""
    factories = {
        "random": RandomOptimizer,
        "de": DifferentialEvolutionOptimizer,
        "tpe": TPEOptimizer,
        "bo": BayesianOptimizationOptimizer,
    }
    try:
        optimizer_type = factories[config.method]
    except KeyError:
        raise ResearchExperimentError(f"research optimizer method '{config.method}' is not implemented") from None
    return optimizer_type(config, seeds)
