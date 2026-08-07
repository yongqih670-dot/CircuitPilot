"""Lightweight Gaussian-process Bayesian optimization adapter."""

from __future__ import annotations

from dataclasses import asdict
from math import exp, pi, sqrt
from pathlib import Path
from typing import Mapping

import numpy as np
from scipy.special import ndtr

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.config import ExperimentConfig, ParameterValue
from circuitpilot.experiments.optimizers.base import (
    Optimizer, OptimizerFeedback, SearchSpaceCodec, read_json_state,
    state_signature, validate_feedback, write_json_state,
)
from circuitpilot.experiments.seeding import SeedContext


class BayesianOptimizationOptimizer(Optimizer):
    """Seeded GP/EI optimizer for continuous and log-continuous dimensions."""

    STATE_SCHEMA_VERSION = 1

    def __init__(self, config: ExperimentConfig, seed_context: SeedContext) -> None:
        if config.method != "bo":
            raise ValueError("BayesianOptimizationOptimizer requires method='bo'")
        self._config = config
        self._rng = seed_context.numpy_rng
        self._codec = SearchSpaceCodec(config)
        self._codec.require_continuous("Bayesian Optimization")
        settings = config.optimizer_config
        self._initial_points = int(settings["initial_random_points"])
        self._pool_size = int(settings["candidate_pool_size"])
        self._xi = float(settings["exploration_xi"])
        self._noise = float(settings["noise"])
        self._pending: dict[str, ParameterValue] | None = None
        self._phase = "initialization"
        self._x: list[list[float]] = []
        self._y: list[float] = []
        self._history: list[OptimizerFeedback] = []

    @staticmethod
    def _kernel(left: np.ndarray, right: np.ndarray) -> np.ndarray:
        distances = np.sqrt(np.maximum(((left[:, None, :] - right[None, :, :]) ** 2).sum(axis=2), 0.0)) / 0.25
        root5 = sqrt(5.0)
        return (1.0 + root5 * distances + 5.0 * distances**2 / 3.0) * np.exp(-root5 * distances)

    def _model_candidate(self) -> dict[str, ParameterValue]:
        x = np.asarray(self._x, dtype=float)
        y = np.asarray(self._y, dtype=float)
        pool = self._rng.random((self._pool_size, self._codec.dimension))
        kernel = self._kernel(x, x) + self._noise * np.eye(len(x))
        try:
            cholesky = np.linalg.cholesky(kernel)
            alpha = np.linalg.solve(cholesky.T, np.linalg.solve(cholesky, y))
            cross = self._kernel(pool, x)
            mean = cross @ alpha
            solved = np.linalg.solve(cholesky, cross.T)
            variance = np.maximum(1.0 - np.sum(solved**2, axis=0), 1e-14)
            sigma = np.sqrt(variance)
            improvement = float(np.min(y)) - mean - self._xi
            z = improvement / sigma
            density = np.exp(-0.5 * z**2) / sqrt(2.0 * pi)
            expected_improvement = improvement * ndtr(z) + sigma * density
            coordinate = pool[int(np.argmax(expected_improvement))]
        except np.linalg.LinAlgError:
            coordinate = pool[0]
        return self._codec.decode(coordinate)

    def ask(self) -> dict[str, ParameterValue]:
        if self._pending is not None:
            raise ResearchExperimentError("optimizer.ask called before previous tell")
        if len(self._history) < self._initial_points or len(self._y) < 2:
            self._phase = "initialization"
            self._pending = self._codec.sample(self._rng)
        else:
            self._phase = "model_based"
            self._pending = self._model_candidate()
        return dict(self._pending)

    def tell(self, parameters: Mapping[str, ParameterValue], metrics: Mapping[str, float], objective: float | None, simulation_status: str) -> None:
        feedback = validate_feedback(self._pending, parameters, metrics, objective, simulation_status)
        if feedback.simulation_status == "success" and feedback.objective is not None:
            self._x.append(self._codec.encode(parameters).tolist())
            self._y.append(feedback.objective)
        self._history.append(feedback)
        self._pending = None

    def get_last_ask_metadata(self) -> dict[str, str]:
        return {"optimizer_phase": self._phase}

    def save_state(self, path: str | Path) -> Path:
        return write_json_state(path, {
            "schema_version": self.STATE_SCHEMA_VERSION, "signature": state_signature(self._config),
            "rng_state": self._rng.bit_generator.state, "pending": self._pending,
            "phase": self._phase, "x": self._x, "y": self._y,
            "history": [asdict(item) for item in self._history],
        })

    def load_state(self, path: str | Path) -> None:
        payload = read_json_state(path)
        if payload.get("schema_version") != self.STATE_SCHEMA_VERSION or payload.get("signature") != state_signature(self._config):
            raise ResearchExperimentError("optimizer state does not match the current experiment configuration")
        try:
            self._rng.bit_generator.state = payload["rng_state"]
            self._pending = payload["pending"]
            self._phase = payload["phase"]
            self._x = payload["x"]
            self._y = [float(value) for value in payload["y"]]
            self._history = [OptimizerFeedback(**item) for item in payload["history"]]
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchExperimentError(f"invalid BO optimizer state: {exc}") from exc

    def get_history(self) -> tuple[OptimizerFeedback, ...]:
        return tuple(self._history)
