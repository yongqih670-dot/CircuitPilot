"""Strict simulation-budget accounting shared by every research method."""

from __future__ import annotations

from dataclasses import dataclass

from circuitpilot.exceptions import ResearchExperimentError


@dataclass(slots=True)
class SimulationBudget:
    """Track candidate slots without allowing an optimizer to exceed the limit."""

    limit: int
    evaluations_total: int = 0
    evaluations_success: int = 0
    evaluations_failed: int = 0
    ngspice_calls: int = 0

    def __post_init__(self) -> None:
        """Validate initial counters, including resumed runs."""
        values = {
            "limit": self.limit,
            "evaluations_total": self.evaluations_total,
            "evaluations_success": self.evaluations_success,
            "evaluations_failed": self.evaluations_failed,
            "ngspice_calls": self.ngspice_calls,
        }
        for name, value in values.items():
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.limit <= 0:
            raise ValueError("limit must be positive")
        if self.evaluations_total > self.limit:
            raise ValueError("initial evaluations exceed simulation budget")
        if self.evaluations_success + self.evaluations_failed != self.evaluations_total:
            raise ValueError("success and failure counters must sum to total")
        if self.ngspice_calls > self.evaluations_total:
            raise ValueError("ngspice_calls cannot exceed evaluations_total")

    @property
    def budget_remaining(self) -> int:
        """Return the exact number of candidate slots still available."""
        return self.limit - self.evaluations_total

    @property
    def exhausted(self) -> bool:
        """Return whether no further candidate may be evaluated."""
        return self.budget_remaining == 0

    def reserve(self) -> int:
        """Atomically consume one candidate slot and return its 1-based index."""
        if self.exhausted:
            raise ResearchExperimentError(
                f"simulation budget {self.limit} has been exhausted"
            )
        self.evaluations_total += 1
        return self.evaluations_total

    def mark_ngspice_call(self) -> None:
        """Record that the reserved candidate launched exactly one ngspice call."""
        if self.ngspice_calls >= self.evaluations_total:
            raise ResearchExperimentError(
                "cannot record an ngspice call without a reserved candidate slot"
            )
        self.ngspice_calls += 1

    def mark_success(self) -> None:
        """Classify the latest unclassified slot as successful."""
        self._require_unclassified()
        self.evaluations_success += 1

    def mark_failure(self) -> None:
        """Classify the latest unclassified slot as failed."""
        self._require_unclassified()
        self.evaluations_failed += 1

    def _require_unclassified(self) -> None:
        """Require one reserved slot that has not received a final status."""
        classified = self.evaluations_success + self.evaluations_failed
        if classified >= self.evaluations_total:
            raise ResearchExperimentError("no reserved evaluation awaits classification")

    def as_dict(self) -> dict[str, int]:
        """Return stable budget statistics for summaries and manifests."""
        return {
            "simulation_budget": self.limit,
            "evaluations_total": self.evaluations_total,
            "evaluations_success": self.evaluations_success,
            "evaluations_failed": self.evaluations_failed,
            "budget_remaining": self.budget_remaining,
            "ngspice_calls": self.ngspice_calls,
        }
