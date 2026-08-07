import pytest

from circuitpilot.experiments.config import experiment_config_from_mapping
from circuitpilot.experiments.objectives import ObjectiveEvaluator


def test_common_objective_and_constraint_math() -> None:
    config = experiment_config_from_mapping(
        {
            "experiment": {
                "name": "objective_math",
                "circuit": "rc_lowpass",
                "method": "random",
                "seed": 0,
                "simulation_budget": 1,
            },
            "search_space": {
                "resistance": {"type": "float", "low": 100, "high": 1000},
                "capacitance": {"type": "float", "low": 1e-9, "high": 1e-6},
            },
            "objectives": {
                "bandwidth": {"type": "target", "target": 10_000}
            },
            "constraints": {
                "gain_db": {"operator": ">=", "threshold": -1.0}
            },
        }
    )

    result = ObjectiveEvaluator(config).evaluate(
        {"bandwidth": 9_000.0, "gain_db": -1.5}
    )

    assert result.objective_value == pytest.approx(0.1)
    assert result.constraint_violation == pytest.approx(0.5)
