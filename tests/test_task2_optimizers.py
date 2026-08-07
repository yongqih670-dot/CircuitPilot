from dataclasses import replace
from pathlib import Path

import pytest

from circuitpilot.experiments.budget import SimulationBudget
from circuitpilot.experiments.config import experiment_config_from_mapping
from circuitpilot.experiments.optimizer import (
    BayesianOptimizationOptimizer,
    DifferentialEvolutionOptimizer,
    Optimizer,
    RandomOptimizer,
    TPEOptimizer,
    create_optimizer,
)
from circuitpilot.experiments.seeding import initialize_seeds


def _config(method: str, seed: int = 7, budget: int = 20, optimizer_config=None):
    return experiment_config_from_mapping({
        "experiment": {
            "name": f"task2_{method}", "circuit": "rc_lowpass", "method": method,
            "seed": seed, "simulation_budget": budget,
        },
        "search_space": {
            "resistance": {"type": "float", "low": 100.0, "high": 100_000.0, "log": True},
            "capacitance": {"type": "float", "low": 1e-10, "high": 1e-5, "log": True},
        },
        "objectives": {"bandwidth": {"type": "target", "target": 10_000.0}},
        "success_criterion": {"metric": "bandwidth", "relative_error_threshold": 0.05},
        "optimizer_config": optimizer_config or {},
        "pvt_config": {},
    })


@pytest.mark.parametrize(
    ("method", "expected_type"),
    (
        ("random", RandomOptimizer),
        ("de", DifferentialEvolutionOptimizer),
        ("tpe", TPEOptimizer),
        ("bo", BayesianOptimizationOptimizer),
    ),
)
def test_all_four_methods_implement_common_optimizer(method: str, expected_type: type[Optimizer]) -> None:
    optimizer = create_optimizer(_config(method), initialize_seeds(7))
    assert isinstance(optimizer, Optimizer)
    assert isinstance(optimizer, expected_type)
    for name in ("ask", "tell", "save_state", "load_state"):
        assert callable(getattr(optimizer, name))


def _sequence(method: str, seed: int, count: int = 12):
    optimizer = create_optimizer(_config(method, seed), initialize_seeds(seed))
    candidates = []
    for _ in range(count):
        candidate = optimizer.ask()
        candidates.append(candidate)
        objective = abs(float(candidate["resistance"]) * float(candidate["capacitance"]) - 1e-5)
        optimizer.tell(candidate, {"algorithm_test_metric": objective}, objective, "success")
    return candidates


def test_random_and_tpe_seed_reproducibility() -> None:
    for method in ("random", "tpe"):
        assert _sequence(method, 17) == _sequence(method, 17)
        assert _sequence(method, 17) != _sequence(method, 18)


def test_random_supports_float_int_categorical_and_log_float() -> None:
    config = experiment_config_from_mapping({
        "experiment": {"name": "mixed_random", "circuit": "rc_lowpass", "method": "random", "seed": 3, "simulation_budget": 4},
        "search_space": {
            "resistance": {"type": "categorical", "choices": [100, 1000, 10000]},
            "capacitance": {"type": "int", "low": 1, "high": 9, "log": False},
        },
        "objectives": {"bandwidth": {"type": "target", "target": 10_000}},
    })
    optimizer = RandomOptimizer(config, initialize_seeds(config.seed))
    for _ in range(4):
        candidate = optimizer.ask()
        assert candidate["resistance"] in {100, 1000, 10000}
        assert isinstance(candidate["capacitance"], int)
        optimizer.tell(candidate, {}, None, "simulation_failed")


def test_de_stops_at_budget_mid_generation() -> None:
    config = _config("de", budget=10, optimizer_config={"population_size": 8})
    optimizer = create_optimizer(config, initialize_seeds(config.seed))
    budget = SimulationBudget(10)
    phases = []
    while not budget.exhausted:
        candidate = optimizer.ask()
        phases.append(optimizer.get_last_ask_metadata()["optimizer_phase"])
        budget.reserve()
        objective = abs(float(candidate["resistance"]) * float(candidate["capacitance"]) - 1e-5)
        optimizer.tell(candidate, {"algorithm_test_metric": objective}, objective, "success")
        budget.mark_success()
    assert budget.evaluations_total == 10
    assert phases.count("initialization") == 8
    assert phases.count("generation") == 2


def test_bo_switches_from_initialization_to_model_based_phase() -> None:
    config = _config("bo", optimizer_config={"initial_random_points": 3, "candidate_pool_size": 64})
    optimizer = create_optimizer(config, initialize_seeds(config.seed))
    phases = []
    for _ in range(5):
        candidate = optimizer.ask()
        phases.append(optimizer.get_last_ask_metadata()["optimizer_phase"])
        objective = abs(float(candidate["resistance"]) * float(candidate["capacitance"]) - 1e-5)
        optimizer.tell(candidate, {"algorithm_test_metric": objective}, objective, "success")
    assert phases[:3] == ["initialization"] * 3
    assert phases[3:] == ["model_based"] * 2


@pytest.mark.parametrize("method", ("random", "de", "tpe", "bo"))
def test_save_load_at_ten_continues_to_twenty_without_duplicate_budget(method: str, tmp_path: Path) -> None:
    config = _config(method, seed=29, budget=20)
    optimizer = create_optimizer(config, initialize_seeds(config.seed))
    budget = SimulationBudget(20)
    first_ten = []
    for _ in range(10):
        candidate = optimizer.ask(); first_ten.append(candidate); budget.reserve()
        objective = abs(float(candidate["resistance"]) * float(candidate["capacitance"]) - 1e-5)
        optimizer.tell(candidate, {"algorithm_test_metric": objective}, objective, "success"); budget.mark_success()
    state = optimizer.save_state(tmp_path / f"{method}.json")

    resumed = create_optimizer(replace(config, simulation_budget=20), initialize_seeds(config.seed))
    resumed.load_state(state)
    resumed_budget = SimulationBudget(20, evaluations_total=10, evaluations_success=10)
    second_ten = []
    while not resumed_budget.exhausted:
        candidate = resumed.ask(); second_ten.append(candidate); resumed_budget.reserve()
        objective = abs(float(candidate["resistance"]) * float(candidate["capacitance"]) - 1e-5)
        resumed.tell(candidate, {"algorithm_test_metric": objective}, objective, "success"); resumed_budget.mark_success()
    assert resumed_budget.evaluations_total == 20
    assert len(resumed.get_history()) == 20

    uninterrupted = create_optimizer(config, initialize_seeds(config.seed))
    expected = []
    for _ in range(20):
        candidate = uninterrupted.ask(); expected.append(candidate)
        objective = abs(float(candidate["resistance"]) * float(candidate["capacitance"]) - 1e-5)
        uninterrupted.tell(candidate, {"algorithm_test_metric": objective}, objective, "success")
    assert first_ten + second_ten == expected
