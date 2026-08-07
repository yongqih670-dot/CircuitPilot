"""Centralized seed initialization and provenance for research methods."""

from __future__ import annotations

from dataclasses import dataclass
import random

import numpy as np


@dataclass(frozen=True, slots=True)
class SeedRegistry:
    """Explicit seeds derived only from ``ExperimentConfig.seed``."""

    experiment: int
    python_random: int
    numpy_legacy: int
    numpy_generator: int
    scipy_random_state: int
    optuna_sampler: int

    def as_dict(self) -> dict[str, int]:
        """Return the complete seed mapping for the research manifest."""
        return {
            "experiment": self.experiment,
            "python_random": self.python_random,
            "numpy_legacy": self.numpy_legacy,
            "numpy_generator": self.numpy_generator,
            "scipy_random_state": self.scipy_random_state,
            "optuna_sampler": self.optuna_sampler,
        }


@dataclass(slots=True)
class SeedContext:
    """Initialized RNG objects and their recorded seed registry."""

    registry: SeedRegistry
    numpy_rng: np.random.Generator


def initialize_seeds(seed: int) -> SeedContext:
    """Initialize every supported RNG family from the one experiment seed.

    SciPy and Optuna are not required by the random baseline, but their future
    adapters must consume the recorded integer from this registry rather than
    inventing module-local seeds.
    """
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    random.seed(seed)
    np.random.seed(seed)
    registry = SeedRegistry(seed, seed, seed, seed, seed, seed)
    return SeedContext(registry=registry, numpy_rng=np.random.default_rng(seed))
