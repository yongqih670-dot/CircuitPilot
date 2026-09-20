from __future__ import annotations

import csv
import gzip
from pathlib import Path

import pytest

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments import task9_batch
from circuitpilot.experiments import task9_runner
from circuitpilot.experiments.task9_batch import _consolidate_evaluations, validate_fairness
from circuitpilot.experiments.task9_evaluator import Task9Evaluation
from circuitpilot.experiments.task9_runner import (
    Task9RunDefinition,
    execute_task9_run,
    fairness_identity,
    validate_frozen_protocol,
)
from circuitpilot.task7_protocol import METHODS, TASK7_BENCHMARK_HASH
from circuitpilot.task9_protocol import PVT_BENCHMARK_HASH, TASK9_PROTOCOL_HASH, policy_hash


ROOT = Path(__file__).resolve().parents[1]
TASK7 = ROOT / "research" / "sky130" / "two_stage_ota" / "task7_frozen.yaml"


def _definition(tmp_path: Path, *, design: str = "equal_candidate", policy: str = "full") -> Task9RunDefinition:
    return Task9RunDefinition(
        base_config_path=TASK7,
        method="random",
        policy=policy,
        seed=9,
        experiment_design=design,
        output_root=tmp_path,
        candidate_budget=2 if design == "equal_candidate" else None,
        simulation_time_budget_seconds=375.0 if design == "equal_simulation_time" else None,
        candidate_cap=5 if design == "equal_simulation_time" else None,
    )


def _fake_evaluation(*, policy: str, **kwargs) -> Task9Evaluation:
    full = policy == "full"
    return Task9Evaluation(
        policy=policy,
        evaluation_stage="complete",
        first_failing_corner=None,
        first_failing_stage=None,
        first_failing_constraint=None,
        simulation_status="success",
        corner_results=(),
        worst_metrics={"dc_gain_db": 20.0},
        objective_value=0.01,
        robust_constraint_violation=0.0,
        constraint_components={},
        is_feasible=True,
        progress_units=45 if full else 3,
        feedback_tier=(1, 45 if full else 3, 0.0),
        corners_started=15 if full else 1,
        corners_completed=15 if full else 1,
        op_calls=15 if full else 1,
        ac_calls=15 if full else 1,
        transient_calls=15 if full else 1,
        process_calls=45 if full else 3,
        accumulated_ngspice_seconds=200.0,
        outer_wall_seconds=0.01,
        orchestration_seconds=0.0,
        process_elapsed_estimate_count=0,
    )


def test_frozen_protocol_manifest_validates() -> None:
    manifest = validate_frozen_protocol()
    assert manifest["hashes"]["task9_protocol_hash"] == TASK9_PROTOCOL_HASH
    assert manifest["hashes"]["pvt_benchmark_hash"] == PVT_BENCHMARK_HASH


def test_all_optimizers_share_the_identical_pvt_benchmark(tmp_path) -> None:
    hashes = {
        Task9RunDefinition(
            base_config_path=TASK7,
            method=method,
            policy="full",
            seed=0,
            experiment_design="smoke",
            output_root=tmp_path,
            candidate_budget=10,
        ).semantic_dict()["pvt_benchmark_hash"]
        for method in METHODS
    }
    assert hashes == {PVT_BENCHMARK_HASH}


def test_runner_resumes_exactly_and_stops_at_candidate_budget(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task9_runner, "evaluate_task9_candidate", _fake_evaluation)
    definition = _definition(tmp_path)
    run_directory, first = execute_task9_run(definition, max_new_candidates=1)
    assert not first["completed"]
    assert first["candidate_count"] == 1
    resumed_directory, final = execute_task9_run(definition, resume_directory=run_directory)
    assert resumed_directory == run_directory
    assert final["completed"]
    assert final["candidate_count"] == 2
    assert final["process_calls"] == 90


def test_equal_time_stops_after_boundary_crossing(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task9_runner, "evaluate_task9_candidate", _fake_evaluation)
    definition = _definition(tmp_path, design="equal_simulation_time")
    _, summary = execute_task9_run(definition)
    assert summary["completed"]
    assert summary["candidate_count"] == 2
    assert summary["accumulated_ngspice_seconds"] == pytest.approx(400.0)
    assert summary["budget_overshoot_seconds"] == pytest.approx(25.0)


def test_paired_fairness_accepts_only_policy_hash_difference(tmp_path) -> None:
    config = load_experiment_config(TASK7)
    summaries = []
    for policy in ("full", "hierarchical"):
        definition = Task9RunDefinition(
            base_config_path=TASK7,
            method="random",
            policy=policy,
            seed=0,
            experiment_design="smoke",
            output_root=tmp_path,
            candidate_budget=10,
            shadow_audit=policy == "hierarchical",
        )
        full = policy == "full"
        summaries.append(
            {
                "experiment_id": definition.experiment_id,
                "policy": policy,
                "method": "random",
                "seed": 0,
                "completed": True,
                "candidate_count": 10,
                "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
                "task9_protocol_hash": TASK9_PROTOCOL_HASH,
                "pvt_benchmark_hash": PVT_BENCHMARK_HASH,
                "fairness_identity": fairness_identity(definition, config),
                "corners_started": 150 if full else 10,
                "corners_completed": 150 if full else 10,
                "op_calls": 150 if full else 10,
                "ac_calls": 150 if full else 10,
                "transient_calls": 150 if full else 10,
                "process_calls": 450 if full else 30,
                "accumulated_ngspice_seconds": 1.0,
                "shadow_false_rejection_count": 0,
            }
        )
    report = validate_fairness(
        summaries, design="smoke", methods=("random",), seeds=(0,)
    )
    assert report["status"] == "pass"
    assert summaries[0]["fairness_identity"]["policy_hash"] == policy_hash("full")
    assert summaries[1]["fairness_identity"]["policy_hash"] == policy_hash("hierarchical")


def test_large_consolidated_evidence_is_losslessly_gzipped(monkeypatch, tmp_path) -> None:
    run = tmp_path / "run"
    run.mkdir()
    with (run / "evaluations.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["candidate", "status"])
        writer.writeheader()
        writer.writerow({"candidate": 1, "status": "success"})
    monkeypatch.setattr(task9_batch, "CONSOLIDATED_CSV_GZIP_THRESHOLD_BYTES", 1)
    destination = tmp_path / "evaluations.csv"
    _consolidate_evaluations([{"_run_directory": str(run)}], destination)
    compressed = tmp_path / "evaluations.csv.gz"
    assert compressed.is_file()
    assert not destination.exists()
    with gzip.open(compressed, "rt", encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == [{"candidate": "1", "status": "success"}]
