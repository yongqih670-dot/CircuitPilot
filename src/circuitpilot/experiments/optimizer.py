"""Optimizer ask/tell contract and deterministic random-search baseline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
import json
from math import isfinite, log10
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.config import ExperimentConfig, ParameterType
from circuitpilot.experiments.seeding import SeedContext


@dataclass(frozen=True, slots=True)
class OptimizerFeedback:
    """One completed candidate reported to an optimizer."""

    parameters: dict[str, float | int]
    metrics: dict[str, float]
    objective: float | None
    simulation_status: str


class Optimizer(ABC):
    """Simulation-independent interface implemented by every research method."""

    @abstractmethod
    def ask(self) -> dict[str, float | int]:
        """Return the next candidate parameters without running a simulation."""

    @abstractmethod
    def tell(
        self,
        parameters: Mapping[str, float | int],
        metrics: Mapping[str, float],
        objective: float | None,
        simulation_status: str,
    ) -> None:
        """Report one completed candidate and its externally measured result."""

    @abstractmethod
    def save_state(self, path: str | Path) -> Path:
        """Persist enough state to continue the exact candidate sequence."""

    @abstractmethod
    def load_state(self, path: str | Path) -> None:
        """Restore a state previously written by ``save_state``."""

    def reset(self) -> None:
        """Reset optional optimizer state when an implementation supports it."""
        raise NotImplementedError

    def get_best(self) -> OptimizerFeedback | None:
        """Return the lowest successful scalar objective, if available."""
        return None

    def get_history(self) -> tuple[OptimizerFeedback, ...]:
        """Return completed ask/tell feedback in deterministic order."""
        return ()


class RandomOptimizer(Optimizer):
    """Uniform/log-uniform random baseline driven only by the shared seed context."""

    STATE_SCHEMA_VERSION = 1

    def __init__(self, config: ExperimentConfig, seed_context: SeedContext) -> None:
        """Bind the common search space to the centrally initialized NumPy RNG."""
        if config.method != "random":
            raise ValueError("RandomOptimizer requires method='random'")
        if config.optimizer_config:
            unknown = ", ".join(sorted(config.optimizer_config))
            raise ValueError(
                f"random optimizer accepts no optimizer_config fields: {unknown}"
            )
        self._config = config
        self._rng = seed_context.numpy_rng
        self._initial_state = json.loads(json.dumps(self._rng.bit_generator.state))
        self._pending: dict[str, float | int] | None = None
        self._history: list[OptimizerFeedback] = []

    def ask(self) -> dict[str, float | int]:
        """Draw one candidate in declared search-space order."""
        if self._pending is not None:
            raise ResearchExperimentError("optimizer.ask called before previous tell")
        candidate: dict[str, float | int] = {}
        for definition in self._config.search_space:
            if definition.log:
                coordinate = self._rng.uniform(log10(definition.low), log10(definition.high))
                sampled = 10.0 ** float(coordinate)
            else:
                sampled = float(self._rng.uniform(definition.low, definition.high))
            if definition.parameter_type is ParameterType.INTEGER:
                integer = int(round(sampled))
                candidate[definition.name] = max(
                    int(definition.low), min(int(definition.high), integer)
                )
            else:
                candidate[definition.name] = sampled
        self._pending = dict(candidate)
        return dict(candidate)

    def tell(
        self,
        parameters: Mapping[str, float | int],
        metrics: Mapping[str, float],
        objective: float | None,
        simulation_status: str,
    ) -> None:
        """Store external feedback without deriving or modifying physical metrics."""
        if self._pending is None:
            raise ResearchExperimentError("optimizer.tell called without a pending ask")
        normalized_parameters = dict(parameters)
        if normalized_parameters != self._pending:
            raise ResearchExperimentError(
                "optimizer.tell parameters do not match the pending candidate"
            )
        if not isinstance(simulation_status, str) or not simulation_status:
            raise ValueError("simulation_status must be a non-empty string")
        normalized_metrics: dict[str, float] = {}
        for name, value in metrics.items():
            if not isinstance(name, str) or not name:
                raise ValueError("optimizer metrics require non-empty names")
            numeric = float(value)
            if not isfinite(numeric):
                raise ValueError(f"optimizer metric '{name}' must be finite")
            normalized_metrics[name] = numeric
        normalized_objective = None if objective is None else float(objective)
        if normalized_objective is not None and not isfinite(normalized_objective):
            raise ValueError("optimizer objective must be finite or null")
        if simulation_status == "success":
            if normalized_objective is None or not normalized_metrics:
                raise ValueError(
                    "successful optimizer feedback requires metrics and objective"
                )
        elif normalized_metrics or normalized_objective is not None:
            raise ValueError(
                "failed optimizer feedback cannot contain physical metrics or objective"
            )
        feedback = OptimizerFeedback(
            parameters=normalized_parameters,
            metrics=normalized_metrics,
            objective=normalized_objective,
            simulation_status=simulation_status,
        )
        self._history.append(feedback)
        self._pending = None

    def save_state(self, path: str | Path) -> Path:
        """Atomically save RNG, pending candidate, and tell history as JSON."""
        destination = Path(path).resolve()
        temporary = destination.with_name(f".{destination.name}.tmp")
        payload = {
            "schema_version": self.STATE_SCHEMA_VERSION,
            "method": "random",
            "seed": self._config.seed,
            "search_space": [
                {
                    "name": item.name,
                    "type": item.parameter_type.value,
                    "low": item.low,
                    "high": item.high,
                    "log": item.log,
                }
                for item in self._config.search_space
            ],
            "rng_state": self._rng.bit_generator.state,
            "pending": self._pending,
            "history": [asdict(item) for item in self._history],
        }
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
                encoding="utf-8",
            )
            temporary.replace(destination)
        except (OSError, TypeError, ValueError) as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ResearchExperimentError(
                f"failed to save optimizer state '{destination}': {exc}"
            ) from exc
        return destination

    def load_state(self, path: str | Path) -> None:
        """Restore state only when method, seed, and search space match exactly."""
        source = Path(path).resolve()
        try:
            payload = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ResearchExperimentError(
                f"failed to load optimizer state '{source}': {exc}"
            ) from exc
        expected_space = [
            {
                "name": item.name,
                "type": item.parameter_type.value,
                "low": item.low,
                "high": item.high,
                "log": item.log,
            }
            for item in self._config.search_space
        ]
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != self.STATE_SCHEMA_VERSION
            or payload.get("method") != "random"
            or payload.get("seed") != self._config.seed
            or payload.get("search_space") != expected_space
        ):
            raise ResearchExperimentError(
                "optimizer state does not match the current experiment configuration"
            )
        try:
            self._rng.bit_generator.state = payload["rng_state"]
            pending = payload.get("pending")
            if pending is not None and not isinstance(pending, dict):
                raise ValueError("pending candidate must be an object or null")
            history = payload.get("history")
            if not isinstance(history, list):
                raise ValueError("history must be a list")
            self._pending = pending
            self._history = [OptimizerFeedback(**item) for item in history]
        except (KeyError, TypeError, ValueError) as exc:
            raise ResearchExperimentError(f"invalid optimizer state: {exc}") from exc

    def reset(self) -> None:
        """Restore the initial RNG state and clear all ask/tell history."""
        self._rng.bit_generator.state = json.loads(json.dumps(self._initial_state))
        self._pending = None
        self._history.clear()

    def get_best(self) -> OptimizerFeedback | None:
        """Return the best successful feedback by minimized scalar objective."""
        successful = [
            item
            for item in self._history
            if item.simulation_status == "success" and item.objective is not None
        ]
        return min(successful, key=lambda item: item.objective) if successful else None

    def get_history(self) -> tuple[OptimizerFeedback, ...]:
        """Return an immutable snapshot of completed feedback."""
        return tuple(self._history)


def create_optimizer(config: ExperimentConfig, seeds: SeedContext) -> Optimizer:
    """Construct the configured method without adding method-specific run logic."""
    if config.method == "random":
        return RandomOptimizer(config, seeds)
    raise ResearchExperimentError(
        f"research optimizer method '{config.method}' is not implemented"
    )
