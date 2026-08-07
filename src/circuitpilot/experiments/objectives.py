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
    relative_error: float | None
    is_feasible: bool


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
            constraint_components[definition.constraint_id or definition.metric] = violation
            total_violation += violation

        objective_components: dict[str, float] = {}
        total_objective = 0.0
        all_constraints_mode = (
            self._config.success_criterion.criterion_type == "all_constraints"
        )
        total_weight = sum(definition.weight for definition in self._config.objectives)
        for definition in self._config.objectives:
            if definition.metric not in normalized:
                raise ResearchExperimentError(
                    f"required objective metric '{definition.metric}' is unavailable"
                )
            metric = normalized[definition.metric]
            if all_constraints_mode:
                matching_threshold = next(
                    (
                        abs(item.threshold)
                        for item in self._config.constraints
                        if item.metric == definition.metric and item.threshold != 0
                    ),
                    1.0,
                )
                scale = max(matching_threshold, 1e-12)
                if definition.objective_type is ObjectiveType.MAXIMIZE:
                    positive = max(metric, 0.0)
                    component = scale / (scale + positive)
                elif definition.objective_type is ObjectiveType.MINIMIZE:
                    positive = max(metric, 0.0)
                    component = positive / (scale + positive)
                else:
                    assert definition.target is not None
                    error = abs(metric - definition.target) / max(
                        abs(definition.target), 1e-12
                    )
                    component = error / (1.0 + error)
            elif definition.objective_type is ObjectiveType.MAXIMIZE:
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

        if all_constraints_mode:
            secondary = total_objective / total_weight
            total_objective = (
                1.0 + total_violation if total_violation > 0.0 else secondary
            )

        if not isfinite(total_objective) or not isfinite(total_violation):
            raise ResearchExperimentError("objective evaluation produced non-finite output")
        criterion = self._config.success_criterion
        if criterion.criterion_type == "all_constraints":
            relative_error = None
            is_feasible = total_violation == 0.0
        else:
            assert criterion.metric is not None
            target = self._config.target_by_metric[criterion.metric]
            relative_error = abs(normalized[criterion.metric] - target) / max(abs(target), 1e-12)
            assert criterion.relative_error_threshold is not None
            is_feasible = (
                relative_error <= criterion.relative_error_threshold
                and total_violation == 0.0
            )
        return ObjectiveEvaluation(
            objective_value=total_objective,
            constraint_violation=total_violation,
            objective_components=objective_components,
            constraint_components=constraint_components,
            relative_error=relative_error,
            is_feasible=is_feasible,
        )
