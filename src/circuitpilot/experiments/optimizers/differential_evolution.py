"""Budget-transparent differential-evolution ask/tell state machine."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.config import ExperimentConfig, ParameterValue
from circuitpilot.experiments.optimizers.base import (
    Optimizer, OptimizerFeedback, SearchSpaceCodec, read_json_state,
    state_signature, validate_feedback, write_json_state,
)
from circuitpilot.experiments.seeding import SeedContext


class DifferentialEvolutionOptimizer(Optimizer):
    """Sequential standard DE whose every candidate is visible to the Runner."""

    STATE_SCHEMA_VERSION = 1

    def __init__(self, config: ExperimentConfig, seed_context: SeedContext) -> None:
        if config.method != "de":
            raise ValueError("DifferentialEvolutionOptimizer requires method='de'")
        self._config = config
        self._rng = seed_context.numpy_rng
        self._codec = SearchSpaceCodec(config)
        self._codec.require_continuous("Differential Evolution")
        settings = config.optimizer_config
        self._population_size = int(settings["population_size"])
        self._mutation = float(settings["mutation"])
        self._recombination = float(settings["recombination"])
        self._strategy = str(settings["strategy"])
        self._population: list[dict[str, ParameterValue]] = []
        self._vectors: list[list[float]] = []
        self._fitness: list[float | None] = []
        self._generation = 0
        self._target_index = 0
        self._generation_vectors: list[list[float]] | None = None
        self._generation_fitness: list[float | None] | None = None
        self._pending: dict[str, Any] | None = None
        self._history: list[OptimizerFeedback] = []

    def ask(self) -> dict[str, ParameterValue]:
        if self._pending is not None:
            raise ResearchExperimentError("optimizer.ask called before previous tell")
        if len(self._population) < self._population_size:
            candidate = self._codec.sample(self._rng)
            vector = self._codec.encode(candidate)
            self._pending = {"kind": "initialization", "candidate": candidate, "vector": vector.tolist()}
            return dict(candidate)
        if self._generation_vectors is None:
            self._generation_vectors = [list(vector) for vector in self._vectors]
            self._generation_fitness = list(self._fitness)
            self._target_index = 0
        trial = self._make_trial(self._target_index)
        candidate = self._codec.decode(trial)
        self._pending = {
            "kind": "generation", "candidate": candidate,
            "vector": trial.tolist(), "target_index": self._target_index,
        }
        return dict(candidate)

    def _make_trial(self, target_index: int) -> np.ndarray:
        assert self._generation_vectors is not None and self._generation_fitness is not None
        vectors = np.asarray(self._generation_vectors, dtype=float)
        available = [index for index in range(self._population_size) if index != target_index]
        if self._strategy == "best1bin":
            valid = [i for i, value in enumerate(self._generation_fitness) if value is not None]
            base_index = min(valid, key=lambda i: float(self._generation_fitness[i])) if valid else int(self._rng.choice(available))
            remaining = [i for i in available if i != base_index]
            first, second = self._rng.choice(remaining, size=2, replace=False)
            mutant = vectors[base_index] + self._mutation * (vectors[first] - vectors[second])
        else:
            first, second, third = self._rng.choice(available, size=3, replace=False)
            mutant = vectors[first] + self._mutation * (vectors[second] - vectors[third])
        mutant = np.clip(mutant, 0.0, 1.0)
        mask = self._rng.random(self._codec.dimension) < self._recombination
        mask[int(self._rng.integers(0, self._codec.dimension))] = True
        target = vectors[target_index]
        return np.where(mask, mutant, target)

    def tell(self, parameters: Mapping[str, ParameterValue], metrics: Mapping[str, float], objective: float | None, simulation_status: str) -> None:
        pending_candidate = None if self._pending is None else self._pending["candidate"]
        feedback = validate_feedback(pending_candidate, parameters, metrics, objective, simulation_status)
        assert self._pending is not None
        vector = list(self._pending["vector"])
        if self._pending["kind"] == "initialization":
            self._population.append(dict(parameters))
            self._vectors.append(vector)
            self._fitness.append(feedback.objective if feedback.simulation_status == "success" else None)
        else:
            index = int(self._pending["target_index"])
            target_fitness = self._fitness[index]
            if feedback.simulation_status == "success" and feedback.objective is not None and (target_fitness is None or feedback.objective <= target_fitness):
                self._population[index] = dict(parameters)
                self._vectors[index] = vector
                self._fitness[index] = feedback.objective
            self._target_index += 1
            if self._target_index == self._population_size:
                self._generation += 1
                self._generation_vectors = None
                self._generation_fitness = None
                self._target_index = 0
        self._history.append(feedback)
        self._pending = None

    def get_last_ask_metadata(self) -> dict[str, str]:
        phase = "initialization" if self._pending is None or self._pending["kind"] == "initialization" else "generation"
        return {"optimizer_phase": phase}

    def save_state(self, path: str | Path) -> Path:
        return write_json_state(path, {
            "schema_version": self.STATE_SCHEMA_VERSION, "signature": state_signature(self._config),
            "rng_state": self._rng.bit_generator.state, "population": self._population,
            "vectors": self._vectors, "fitness": self._fitness, "generation": self._generation,
            "target_index": self._target_index, "generation_vectors": self._generation_vectors,
            "generation_fitness": self._generation_fitness, "pending": self._pending,
            "history": [asdict(item) for item in self._history],
        })

    def load_state(self, path: str | Path) -> None:
        payload = read_json_state(path)
        if payload.get("schema_version") != self.STATE_SCHEMA_VERSION or payload.get("signature") != state_signature(self._config):
            raise ResearchExperimentError("optimizer state does not match the current experiment configuration")
        try:
            self._rng.bit_generator.state = payload["rng_state"]
            self._population = payload["population"]
            self._vectors = payload["vectors"]
            self._fitness = payload["fitness"]
            self._generation = int(payload["generation"])
            self._target_index = int(payload["target_index"])
            self._generation_vectors = payload["generation_vectors"]
            self._generation_fitness = payload["generation_fitness"]
            self._pending = payload["pending"]
            self._history = [OptimizerFeedback(**item) for item in payload["history"]]
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchExperimentError(f"invalid DE optimizer state: {exc}") from exc

    def get_history(self) -> tuple[OptimizerFeedback, ...]:
        return tuple(self._history)
