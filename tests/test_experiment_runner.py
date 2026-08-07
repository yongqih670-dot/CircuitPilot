from pathlib import Path
from typing import Mapping

from circuitpilot.exceptions import SimulationError
from circuitpilot.experiments.budget import SimulationBudget
from circuitpilot.experiments.config import experiment_config_from_mapping
from circuitpilot.experiments.objectives import ObjectiveEvaluator
from circuitpilot.experiments.optimizer import Optimizer
from circuitpilot.experiments.recorder import EvaluationRecorder
from circuitpilot.experiments.runner import ExperimentRunner
from circuitpilot.experiments.seeding import initialize_seeds
from circuitpilot.run_directory import prepare_research_run_directory


def _config(tmp_path: Path, budget: int = 2):
    return experiment_config_from_mapping(
        {
            "experiment": {
                "name": "runner_contract",
                "circuit": "rc_lowpass",
                "method": "sequence_test",
                "seed": 0,
                "simulation_budget": budget,
                "output_dir": str(tmp_path),
            },
            "search_space": {
                "resistance": {"type": "float", "low": 100, "high": 10_000},
                "capacitance": {"type": "float", "low": 1e-9, "high": 1e-6},
            },
            "objectives": {
                "bandwidth": {"type": "target", "target": 10_000}
            },
        }
    )


class SequenceOptimizer(Optimizer):
    def __init__(self, candidates):
        self.candidates = list(candidates)
        self.index = 0
        self.feedback = []

    def ask(self):
        candidate = dict(self.candidates[self.index])
        self.index += 1
        return candidate

    def tell(self, parameters, metrics, objective, simulation_status):
        self.feedback.append((dict(parameters), dict(metrics), objective, simulation_status))

    def save_state(self, path):
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(str(self.index), encoding="utf-8")
        return destination

    def load_state(self, path):
        self.index = int(Path(path).read_text(encoding="utf-8"))


class MustNotRunSimulator:
    def __init__(self):
        self.call_count = 0

    def evaluate(self, parameters, evaluation_directory, on_ngspice_launch):
        self.call_count += 1
        raise AssertionError("invalid parameters must not reach the simulator")


class LaunchFailureSimulator:
    def __init__(self):
        self.call_count = 0

    def evaluate(self, parameters, evaluation_directory, on_ngspice_launch):
        self.call_count += 1
        on_ngspice_launch()
        raise SimulationError("ngspice process failed")


class MustNotAnalyze:
    def extract(self, simulation, parameters: Mapping[str, float | int]):
        raise AssertionError("failed simulations must not reach the analyzer")


def _runner(tmp_path: Path, config, optimizer, simulator):
    run = prepare_research_run_directory(tmp_path / "run")
    seeds = initialize_seeds(config.seed)
    recorder = EvaluationRecorder(run.path)
    return ExperimentRunner(
        config=config,
        run=run,
        optimizer=optimizer,
        simulator=simulator,
        analyzer=MustNotAnalyze(),
        objective_evaluator=ObjectiveEvaluator(config),
        recorder=recorder,
        budget=SimulationBudget(config.simulation_budget),
        seed_registry=seeds.registry,
        optimizer_state_path=run.path / "summary" / "optimizer_state.json",
    )


def test_invalid_parameters_never_call_simulator(tmp_path: Path) -> None:
    config = _config(tmp_path, budget=1)
    optimizer = SequenceOptimizer(
        [{"resistance": -1.0, "capacitance": 1e-7}]
    )
    simulator = MustNotRunSimulator()

    result = _runner(tmp_path, config, optimizer, simulator).run_to_budget()

    assert simulator.call_count == 0
    assert result.budget["evaluations_failed"] == 1
    assert result.budget["ngspice_calls"] == 0
    assert result.records[0].simulation_status == "invalid_parameters"


def test_runner_uses_optimizer_interface_and_failed_launches_consume_budget(
    tmp_path: Path,
) -> None:
    config = _config(tmp_path, budget=2)
    candidates = [
        {"resistance": 1000.0, "capacitance": 1e-7},
        {"resistance": 2000.0, "capacitance": 2e-7},
    ]
    optimizer = SequenceOptimizer(candidates)
    simulator = LaunchFailureSimulator()

    result = _runner(tmp_path, config, optimizer, simulator).run_to_budget()

    assert simulator.call_count == 2
    assert len(optimizer.feedback) == 2
    assert result.budget["evaluations_total"] == 2
    assert result.budget["evaluations_failed"] == 2
    assert result.budget["budget_remaining"] == 0
    assert result.budget["ngspice_calls"] == 2
    assert all(record.objective_value is None for record in result.records)
