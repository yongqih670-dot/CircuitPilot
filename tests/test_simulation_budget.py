import pytest

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.budget import SimulationBudget


def test_budget_cannot_be_exceeded_and_failures_consume_slots() -> None:
    budget = SimulationBudget(limit=2)

    assert budget.reserve() == 1
    budget.mark_ngspice_call()
    budget.mark_failure()
    assert budget.reserve() == 2
    budget.mark_ngspice_call()
    budget.mark_success()

    assert budget.as_dict() == {
        "simulation_budget": 2,
        "evaluations_total": 2,
        "evaluations_success": 1,
        "evaluations_failed": 1,
        "budget_remaining": 0,
        "ngspice_calls": 2,
    }
    with pytest.raises(ResearchExperimentError, match="exhausted"):
        budget.reserve()
