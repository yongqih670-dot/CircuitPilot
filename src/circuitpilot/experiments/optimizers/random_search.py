"""Deterministic random-search baseline."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Mapping

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.config import ExperimentConfig, ParameterValue
from circuitpilot.experiments.optimizers.base import (
    Optimizer,
    OptimizerFeedback,
    SearchSpaceCodec,
    read_json_state,
    state_signature,
    validate_feedback,
    write_json_state,
)
from circuitpilot.experiments.seeding import SeedContext


class RandomOptimizer(Optimizer):
    """Uniform/log-uniform/categorical sampling from the centralized RNG."""

    STATE_SCHEMA_VERSION = 2

    def __init__(self, config: ExperimentConfig, seed_context: SeedContext) -> None:
        if config.method != "random":
            raise ValueError("RandomOptimizer requires method='random'")
        self._config = config
        self._rng = seed_context.numpy_rng
        self._codec = SearchSpaceCodec(config)
        self._initial_state = json.loads(json.dumps(self._rng.bit_generator.state))
        self._pending: dict[str, ParameterValue] | None = None
        self._history: list[OptimizerFeedback] = []

    def ask(self) -> dict[str, ParameterValue]:
        if self._pending is not None:
            raise ResearchExperimentError("optimizer.ask called before previous tell")
        self._pending = self._codec.sample(self._rng)
        return dict(self._pending)

    def tell(self, parameters: Mapping[str, ParameterValue], metrics: Mapping[str, float], objective: float | None, simulation_status: str) -> None:
        feedback = validate_feedback(self._pending, parameters, metrics, objective, simulation_status)
        self._history.append(feedback)
        self._pending = None

    def save_state(self, path: str | Path) -> Path:
        return write_json_state(path, {
            "schema_version": self.STATE_SCHEMA_VERSION,
            "signature": state_signature(self._config),
            "rng_state": self._rng.bit_generator.state,
            "pending": self._pending,
            "history": [asdict(item) for item in self._history],
        })

    def load_state(self, path: str | Path) -> None:
        payload = read_json_state(path)
        if payload.get("schema_version") != self.STATE_SCHEMA_VERSION or payload.get("signature") != state_signature(self._config):
            raise ResearchExperimentError("optimizer state does not match the current experiment configuration")
        try:
            self._rng.bit_generator.state = payload["rng_state"]
            self._pending = payload["pending"]
            self._history = [OptimizerFeedback(**item) for item in payload["history"]]
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchExperimentError(f"invalid random optimizer state: {exc}") from exc

    def reset(self) -> None:
        self._rng.bit_generator.state = json.loads(json.dumps(self._initial_state))
        self._pending = None
        self._history.clear()

    def get_history(self) -> tuple[OptimizerFeedback, ...]:
        return tuple(self._history)

    def get_last_ask_metadata(self) -> dict[str, str]:
        return {"optimizer_phase": "random"}
