from pathlib import Path

from circuitpilot.experiments.config import experiment_config_from_mapping
from circuitpilot.experiments.optimizer import RandomOptimizer
from circuitpilot.experiments.seeding import initialize_seeds


def _config(seed: int = 7):
    return experiment_config_from_mapping(
        {
            "experiment": {
                "name": "optimizer_contract",
                "circuit": "rc_lowpass",
                "method": "random",
                "seed": seed,
                "simulation_budget": 4,
            },
            "search_space": {
                "resistance": {
                    "type": "float",
                    "low": 100.0,
                    "high": 10_000.0,
                    "log": True,
                },
                "capacitance": {
                    "type": "float",
                    "low": 1e-9,
                    "high": 1e-6,
                    "log": True,
                },
            },
            "objectives": {
                "bandwidth": {"type": "target", "target": 10_000.0}
            },
        }
    )


def _candidate_sequence(seed: int, count: int = 4):
    config = _config(seed)
    optimizer = RandomOptimizer(config, initialize_seeds(seed))
    candidates = []
    for _ in range(count):
        candidate = optimizer.ask()
        candidates.append(candidate)
        optimizer.tell(candidate, {}, None, "simulation_failed")
    return candidates


def test_same_seed_produces_the_same_candidate_sequence() -> None:
    assert _candidate_sequence(17) == _candidate_sequence(17)
    assert _candidate_sequence(17) != _candidate_sequence(18)


def test_ask_tell_and_state_resume_preserve_sequence(tmp_path: Path) -> None:
    config = _config(23)
    uninterrupted = RandomOptimizer(config, initialize_seeds(23))
    first = uninterrupted.ask()
    uninterrupted.tell(first, {}, None, "simulation_failed")
    expected_next = uninterrupted.ask()

    interrupted = RandomOptimizer(config, initialize_seeds(23))
    candidate = interrupted.ask()
    interrupted.tell(candidate, {}, None, "simulation_failed")
    state = interrupted.save_state(tmp_path / "optimizer_state.json")
    resumed = RandomOptimizer(config, initialize_seeds(23))
    resumed.load_state(state)

    assert candidate == first
    assert resumed.ask() == expected_next
    assert len(resumed.get_history()) == 1
