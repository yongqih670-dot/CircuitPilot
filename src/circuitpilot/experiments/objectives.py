"""Common objective and constraint evaluation over measured metrics."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.config import (
    ConstraintOperator,
    ExperimentConfig,
    ObjectiveType,
)


@dataclass(frozen=True, slots=True)
class ObjectiveEvaluation:
    """Scalar optimizer feedback plus transparent component breakdowns."""

    objective_value: float
    constraint_violation: float
    objective_components: dict[str, float]
    constraint_components: dict[str, float]


class ObjectiveEvaluator:
    """Evaluate all methods with the same scalar objective and constraints."""

    def __init__(self, config: ExperimentConfig) -> None:
        """Bind the common objective/constraint definitions."""
        self._config = config

    def evaluate(self, metrics: Mapping[str, float]) -> ObjectiveEvaluation:
        """Convert measured physical metrics into optimizer-facing scalars."""
        normalized: dict[str, float] = {}
        for name, value in metrics.items():
            numeric = float(value)
            if not isfinite(numeric):
                raise ResearchExperimentError(f"metric '{name}' must be finite")
            normalized[name] = numeric

        objective_components: dict[str, float] = {}
        total_objective = 0.0
        for definition in self._config.objectives:
            if definition.metric not in normalized:
                raise ResearchExperimentError(
                    f"required objective metric '{definition.metric}' is unavailable"
                )
            metric = normalized[definition.metric]
            if definition.objective_type is ObjectiveType.MAXIMIZE:
                component = -metric
            elif definition.objective_type is ObjectiveType.MINIMIZE:
                component = metric
            else:
                assert definition.target is not None
                denominator = max(abs(definition.target), 1e-12)
                component = abs(metric - definition.target) / denominator
            weighted = definition.weight * component
            objective_components[definition.metric] = weighted
            total_objective += weighted

        constraint_components: dict[str, float] = {}
        total_violation = 0.0
        for definition in self._config.constraints:
            if definition.metric not in normalized:
                raise ResearchExperimentError(
                    f"required constraint metric '{definition.metric}' is unavailable"
                )
            metric = normalized[definition.metric]
            scale = max(abs(definition.threshold), 1e-12)
            if definition.operator is ConstraintOperator.GREATER_EQUAL:
                violation = max(0.0, definition.threshold - metric) / scale
            else:
                violation = max(0.0, metric - definition.threshold) / scale
            constraint_components[definition.metric] = violation
            total_violation += violation

        if not isfinite(total_objective) or not isfinite(total_violation):
            raise ResearchExperimentError("objective evaluation produced non-finite output")
        return ObjectiveEvaluation(
            objective_value=total_objective,
            constraint_violation=total_violation,
            objective_components=objective_components,
            constraint_components=constraint_components,
        )
