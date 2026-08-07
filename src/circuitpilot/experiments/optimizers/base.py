"""Common optimizer contract, feedback validation, and search-space encoding."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
from math import isfinite, log10
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.config import (
    ExperimentConfig,
    ParameterType,
    ParameterValue,
)


@dataclass(frozen=True, slots=True)
class OptimizerFeedback:
    """One completed candidate reported to an optimizer."""

    parameters: dict[str, ParameterValue]
    metrics: dict[str, float]
    objective: float | None
    simulation_status: str


class Optimizer(ABC):
    """Simulation-independent interface implemented by every research method."""

    @abstractmethod
    def ask(self) -> dict[str, ParameterValue]:
        """Return the next candidate without invoking a simulator."""

    @abstractmethod
    def tell(
        self,
        parameters: Mapping[str, ParameterValue],
        metrics: Mapping[str, float],
        objective: float | None,
        simulation_status: str,
    ) -> None:
        """Report one externally evaluated candidate."""

    @abstractmethod
    def save_state(self, path: str | Path) -> Path:
        """Persist enough state to continue the exact candidate sequence."""

    @abstractmethod
    def load_state(self, path: str | Path) -> None:
        """Restore state previously written by :meth:`save_state`."""

    def reset(self) -> None:
        raise NotImplementedError

    def get_best(self) -> OptimizerFeedback | None:
        successful = [
            item for item in self.get_history()
            if item.simulation_status == "success" and item.objective is not None
        ]
        return min(successful, key=lambda item: float(item.objective)) if successful else None

    def get_history(self) -> tuple[OptimizerFeedback, ...]:
        return ()

    def get_last_ask_metadata(self) -> dict[str, str]:
        """Expose method-neutral metadata for the latest candidate record."""
        return {"optimizer_phase": "search"}


def validate_feedback(
    pending: Mapping[str, ParameterValue] | None,
    parameters: Mapping[str, ParameterValue],
    metrics: Mapping[str, float],
    objective: float | None,
    simulation_status: str,
) -> OptimizerFeedback:
    """Validate the invariant shared by every optimizer's ``tell`` method."""
    if pending is None:
        raise ResearchExperimentError("optimizer.tell called without a pending ask")
    normalized_parameters = dict(parameters)
    if normalized_parameters != dict(pending):
        raise ResearchExperimentError("optimizer.tell parameters do not match the pending candidate")
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
            raise ValueError("successful optimizer feedback requires metrics and objective")
    elif normalized_metrics or normalized_objective is not None:
        raise ValueError("failed optimizer feedback cannot contain physical metrics or objective")
    return OptimizerFeedback(
        parameters=normalized_parameters,
        metrics=normalized_metrics,
        objective=normalized_objective,
        simulation_status=simulation_status,
    )


class SearchSpaceCodec:
    """Sample all supported dimensions and encode numeric spaces to a unit cube."""

    def __init__(self, config: ExperimentConfig) -> None:
        self.definitions = config.search_space

    @property
    def dimension(self) -> int:
        return len(self.definitions)

    def sample(self, rng: np.random.Generator) -> dict[str, ParameterValue]:
        candidate: dict[str, ParameterValue] = {}
        for definition in self.definitions:
            if definition.parameter_type is ParameterType.CATEGORICAL:
                candidate[definition.name] = definition.choices[int(rng.integers(0, len(definition.choices)))]
                continue
            assert definition.low is not None and definition.high is not None
            if definition.log:
                sampled = 10.0 ** float(rng.uniform(log10(definition.low), log10(definition.high)))
            elif definition.parameter_type is ParameterType.INTEGER:
                sampled = int(rng.integers(int(definition.low), int(definition.high) + 1))
            else:
                sampled = float(rng.uniform(definition.low, definition.high))
            if definition.parameter_type is ParameterType.INTEGER:
                sampled = max(int(definition.low), min(int(definition.high), int(round(sampled))))
            candidate[definition.name] = sampled
        return candidate

    def require_continuous(self, method: str) -> None:
        unsupported = [item.name for item in self.definitions if item.parameter_type is not ParameterType.FLOAT]
        if unsupported:
            raise ValueError(f"{method} currently supports only float dimensions; unsupported: {', '.join(unsupported)}")

    def encode(self, parameters: Mapping[str, ParameterValue]) -> np.ndarray:
        coordinates = []
        for definition in self.definitions:
            if definition.parameter_type is ParameterType.CATEGORICAL:
                raise ValueError("categorical dimensions cannot be unit-cube encoded")
            assert definition.low is not None and definition.high is not None
            value = float(parameters[definition.name])
            if definition.log:
                coordinate = (log10(value) - log10(definition.low)) / (log10(definition.high) - log10(definition.low))
            else:
                coordinate = (value - definition.low) / (definition.high - definition.low)
            coordinates.append(float(np.clip(coordinate, 0.0, 1.0)))
        return np.asarray(coordinates, dtype=float)

    def decode(self, coordinates: np.ndarray) -> dict[str, ParameterValue]:
        if len(coordinates) != len(self.definitions):
            raise ValueError("unit-cube coordinate dimension mismatch")
        result: dict[str, ParameterValue] = {}
        for coordinate, definition in zip(coordinates, self.definitions):
            if definition.parameter_type is ParameterType.CATEGORICAL:
                raise ValueError("categorical dimensions cannot be unit-cube decoded")
            assert definition.low is not None and definition.high is not None
            unit = float(np.clip(coordinate, 0.0, 1.0))
            if definition.log:
                value = 10.0 ** (log10(definition.low) + unit * (log10(definition.high) - log10(definition.low)))
            else:
                value = definition.low + unit * (definition.high - definition.low)
            result[definition.name] = int(round(value)) if definition.parameter_type is ParameterType.INTEGER else float(value)
        return result


def state_signature(config: ExperimentConfig) -> dict[str, Any]:
    """Return fields that must match before loading optimizer state."""
    return {
        "method": config.method,
        "seed": config.seed,
        "search_space": [item.to_dict() | {"name": item.name} for item in config.search_space],
        "optimizer_config": dict(config.optimizer_config),
    }


def write_json_state(path: str | Path, payload: Mapping[str, Any]) -> Path:
    destination = Path(path).resolve()
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        temporary.replace(destination)
    except (OSError, TypeError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise ResearchExperimentError(f"failed to save optimizer state '{destination}': {exc}") from exc
    return destination


def read_json_state(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve()
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResearchExperimentError(f"failed to load optimizer state '{source}': {exc}") from exc
    if not isinstance(payload, dict):
        raise ResearchExperimentError("optimizer state root must be an object")
    return payload
