import csv
from dataclasses import replace
import json
from pathlib import Path

import pytest

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments.analyzer import RCLowPassAnalyzer
from circuitpilot.experiments.budget import SimulationBudget
from circuitpilot.experiments.objectives import ObjectiveEvaluator
from circuitpilot.experiments.optimizer import RandomOptimizer
from circuitpilot.experiments.recorder import EVALUATION_COLUMNS, EvaluationRecorder
from circuitpilot.experiments.runner import ExperimentRunner, execute_experiment
from circuitpilot.experiments.seeding import initialize_seeds
from circuitpilot.parser import parse_ac_output
from circuitpilot.analysis import find_cutoff_frequency
from circuitpilot.run_directory import prepare_research_run_directory
from circuitpilot.simulator import resolve_ngspice_executable, run_ngspice


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NGSPICE_EXECUTABLE = resolve_ngspice_executable("ngspice")


@pytest.mark.integration
@pytest.mark.skipif(
    NGSPICE_EXECUTABLE is None,
    reason="real ngspice is required for the unified research experiment",
)
@pytest.mark.parametrize("seed", (0, 1))
def test_unified_random_experiment_uses_real_ngspice_evidence(
    tmp_path: Path, seed: int
) -> None:
    """Verify config -> ask -> ngspice -> analysis -> tell -> CSV/DB/manifest."""
    source = PROJECT_ROOT / "research" / "configs" / f"rc_baseline_seed{seed}.yaml"
    config = replace(
        load_experiment_config(source),
        output_dir=tmp_path / f"seed_{seed}",
        ngspice_config=replace(
            load_experiment_config(source).ngspice_config,
            executable=NGSPICE_EXECUTABLE or "ngspice",
        ),
    )

    result = execute_experiment(config)

    assert result.budget == {
        "simulation_budget": 10,
        "evaluations_total": 10,
        "evaluations_success": 10,
        "evaluations_failed": 0,
        "budget_remaining": 0,
        "ngspice_calls": 10,
    }
    assert len(result.records) == 10
    assert result.best_record is not None
    assert all(record.simulation_status == "success" for record in result.records)
    assert all(record.ngspice_called for record in result.records)

    for record in result.records:
        evidence = result.output_directory / record.run_directory
        response = parse_ac_output(evidence / "ac_results.dat")
        measured = find_cutoff_frequency(response.frequency_hz, response.gain_db)
        assert measured == pytest.approx(record.raw_metrics["bandwidth"], rel=1e-12)
        assert (evidence / "rc_lowpass.cir").is_file()
        assert "ngspice" in (evidence / "ngspice.log").read_text(
            encoding="utf-8", errors="replace"
        ).lower()

    with (result.output_directory / "evaluations.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        reader = csv.DictReader(stream)
        csv_rows = list(reader)
    assert tuple(reader.fieldnames or ()) == EVALUATION_COLUMNS
    assert len(csv_rows) == 10
    assert all(row["objective_value"] for row in csv_rows)
    assert all(json.loads(row["raw_metrics"])["bandwidth"] > 0 for row in csv_rows)
    assert len(EvaluationRecorder(result.output_directory).records()) == 10

    manifest = json.loads(
        (result.output_directory / "research_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["workflow"] == "research_experiment"
    assert manifest["run"]["run_id"] == result.run_id
    assert manifest["reproducibility"]["random_seed"] == seed
    assert set(manifest["reproducibility"]["seeds"]) == {
        "experiment",
        "python_random",
        "numpy_legacy",
        "numpy_generator",
        "scipy_random_state",
        "optuna_sampler",
    }
    assert set(manifest["reproducibility"]["seeds"].values()) == {seed}
    assert manifest["metrics"]["evaluations_total"] == 10
    assert manifest["metrics"]["ngspice_calls"] == 10
    artifact_paths = {item["path"] for item in manifest["artifacts"]}
    assert "experiment_config.yaml" in artifact_paths
    assert "evaluations.csv" in artifact_paths
    assert "evaluations.sqlite3" in artifact_paths
    assert "runs/evaluation_0001/ac_results.dat" in artifact_paths
    assert "summary/optimizer_state.json" in artifact_paths
    assert "plots/objective_progress.png" in artifact_paths


class RealNgspiceFailureSimulator:
    """Launch real ngspice on an invalid netlist to verify failure accounting."""

    def evaluate(self, parameters, evaluation_directory, on_ngspice_launch):
        evaluation_directory.mkdir(parents=True, exist_ok=True)
        netlist = evaluation_directory / "invalid.cir"
        log = evaluation_directory / "ngspice.log"
        netlist.write_text(
            "* Deliberately invalid real-ngspice budget test\n"
            "R1 in out not_a_component_value\n"
            ".ac dec 10 1 1000\n"
            ".end\n",
            encoding="utf-8",
        )
        on_ngspice_launch()
        run_ngspice(
            netlist,
            executable=NGSPICE_EXECUTABLE or "ngspice",
            log_path=log,
        )
        raise AssertionError("invalid netlist unexpectedly succeeded")


@pytest.mark.integration
@pytest.mark.skipif(
    NGSPICE_EXECUTABLE is None,
    reason="real ngspice is required for failure-budget verification",
)
def test_real_ngspice_failure_consumes_exactly_one_budget_slot(tmp_path: Path) -> None:
    base = load_experiment_config(
        PROJECT_ROOT / "research" / "configs" / "rc_baseline_seed0.yaml"
    )
    config = replace(
        base,
        simulation_budget=1,
        output_dir=tmp_path,
        ngspice_config=replace(
            base.ngspice_config, executable=NGSPICE_EXECUTABLE or "ngspice"
        ),
    )
    run = prepare_research_run_directory(tmp_path / "real_failure")
    seeds = initialize_seeds(config.seed)
    recorder = EvaluationRecorder(run.path)
    runner = ExperimentRunner(
        config=config,
        run=run,
        optimizer=RandomOptimizer(config, seeds),
        simulator=RealNgspiceFailureSimulator(),
        analyzer=RCLowPassAnalyzer(config),
        objective_evaluator=ObjectiveEvaluator(config),
        recorder=recorder,
        budget=SimulationBudget(1),
        seed_registry=seeds.registry,
        optimizer_state_path=run.path / "summary" / "optimizer_state.json",
    )

    result = runner.run_to_budget()

    assert result.budget["evaluations_total"] == 1
    assert result.budget["evaluations_failed"] == 1
    assert result.budget["ngspice_calls"] == 1
    assert result.budget["budget_remaining"] == 0
    assert result.records[0].simulation_status == "simulation_failed"
    assert result.records[0].failure_type == "SimulationError"
    assert result.records[0].raw_metrics == {}
    assert result.records[0].objective_value is None
