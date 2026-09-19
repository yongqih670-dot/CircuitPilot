from hashlib import sha256
import json
from pathlib import Path

import pytest

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments.task8_evaluator import (
    StageBoundaryReached,
    StageMeasurement,
    Task8Evaluation,
    evaluate_task8_candidate,
)
from circuitpilot.experiments.task8_runner import (
    Task8RunDefinition,
    execute_task8_run,
    fairness_identity,
    validate_frozen_protocol,
)
from circuitpilot.simulator import resolve_ngspice_executable
from circuitpilot.sky130_two_stage_ota import evaluate_task7_full_candidate
from circuitpilot.task7_protocol import evaluate_task7_objective
from circuitpilot.task8_protocol import (
    CANONICAL_METRICS,
    TASK8_SPECIFICATION,
    hierarchical_objective,
    replay_decision,
)


ROOT = Path("research/sky130/two_stage_ota")
FROZEN = ROOT / "task7_frozen.yaml"
FORMAL = ROOT / "results" / "formal"
TASK8 = ROOT / "task8"


@pytest.fixture
def config():
    return load_experiment_config(FROZEN)


@pytest.fixture
def parameters():
    return {
        "input_pair_width_m": 8e-6,
        "input_pair_length_m": 0.5e-6,
        "first_stage_load_width_m": 12e-6,
        "first_stage_load_length_m": 0.6e-6,
        "tail_width_m": 8e-6,
        "tail_length_m": 0.6e-6,
        "second_stage_width_m": 20e-6,
        "second_stage_length_m": 0.5e-6,
        "second_load_width_m": 20e-6,
        "second_load_length_m": 0.5e-6,
        "second_load_bias_v": 0.8,
        "compensation_capacitance_f": 1e-12,
    }


def _fake_stage_runner(*, op_valid=True, ac_valid=True, transient_valid=True):
    calls = []

    def run(kind, _directory):
        calls.append(kind)
        if kind == "op":
            return StageMeasurement(
                kind,
                {
                    "dc_power_w": 2e-4,
                    "supply_current_a": 1e-4,
                    "output_dc_voltage": 0.9,
                    "stage1_dc_voltage": 0.8,
                    "operating_region_valid": 1.0 if op_valid else 0.0,
                },
                {},
                {
                    "operating_region_valid": op_valid,
                    "operating_region_mask": 0 if op_valid else 1,
                    "operating_region_types": [] if op_valid else ["input_plus:triode"],
                    "device_status": {},
                    "device_quantities": {},
                },
                None,
                0.1,
                0.11,
            )
        if kind == "ac":
            return StageMeasurement(
                kind,
                {
                    "dc_gain_db": 20.0 if ac_valid else 5.0,
                    "ugf_hz": 2e6,
                    "ugf_lower_bound_hz": None,
                    "phase_margin_deg": 60.0,
                    "minus_3db_bandwidth_hz": 1e5,
                },
                {
                    "ugf_status": "measured",
                    "phase_margin_status": "measured",
                    "ugf_crossing_count": 1,
                },
                {},
                None,
                0.2,
                0.22,
            )
        return StageMeasurement(
            kind,
            {
                "positive_slew_v_per_s": 2e6 if transient_valid else 1e5,
                "negative_slew_v_per_s": 2e6,
            },
            {
                "positive_slew_status": "measured",
                "negative_slew_status": "measured",
            },
            {},
            None,
            0.3,
            0.33,
        )

    return run, calls


def _evaluate(tmp_path, config, parameters, runner, **updates):
    values = {
        "policy": "hierarchical",
        "executable": "unused",
        "timeout_seconds": 60.0,
        "start_frequency_hz": 10.0,
        "stop_frequency_hz": 1e10,
        "points_per_decade": 30,
        "stage_runner": runner,
    }
    values.update(updates)
    return evaluate_task8_candidate(
        config.circuit_config, parameters, tmp_path / "evaluation", **values
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    (
        (ROOT / "task7_frozen.yaml", "077a42c053dfa59b6deb6e19dbca6cd74bec8122ebcb17998b906a4aa590df28"),
        (ROOT / "task7_protocol_manifest.json", "edc0be16889aa111a4fc4d0845db0488820b1e00227bf19e9007f61c547da830"),
        (ROOT / "results" / "file_hashes.json", "9d29f304849336d0db06f27fec285b483ce08d0ee1884465d795a9808bc90f78"),
        (ROOT / "TASK7_TWO_STAGE_OTA_REPORT.md", "76af5cf58c524f69d793358ad20759c2c56e77ad3245cabe24cee70521f91b8f"),
        (ROOT / "calibration.csv", "27d0603b460005c9fe9e89a584a2850548bd7c8fb31a9917aa09994bf45883ef"),
        (Path("src/circuitpilot/sky130_two_stage_ota.py"), "8d7036df107854d1cc0c33d3841f705454e4df91527695f18b9cd32730a9db7d"),
    ),
)
def test_task7_frozen_bytes_unchanged(path, expected):
    assert sha256(path.read_bytes()).hexdigest() == expected


def test_frozen_task8_protocol_bytes_validate():
    assert validate_frozen_protocol()["replay_false_rejection_count"] == 0


def test_op_failure_prevents_ac_and_transient_and_preserves_nulls(
    tmp_path, config, parameters
):
    runner, calls = _fake_stage_runner(op_valid=False)
    result = _evaluate(tmp_path, config, parameters, runner)
    assert calls == ["op"]
    assert result.evaluation_stage == "op_rejected"
    assert result.first_blocking_constraint == "operating_region"
    assert all(
        result.metrics[name] is None
        for name in (
            "dc_gain_db",
            "ugf_hz",
            "phase_margin_deg",
            "positive_slew_v_per_s",
            "negative_slew_v_per_s",
        )
    )
    assert (result.op_calls, result.ac_calls, result.transient_calls) == (1, 0, 0)


def test_op_pass_triggers_ac_and_ac_failure_prevents_transient(
    tmp_path, config, parameters
):
    runner, calls = _fake_stage_runner(ac_valid=False)
    result = _evaluate(tmp_path, config, parameters, runner)
    assert calls == ["op", "ac"]
    assert result.evaluation_stage == "ac_rejected"
    assert result.first_blocking_constraint == "gain"
    assert result.metrics["positive_slew_v_per_s"] is None
    assert (result.op_calls, result.ac_calls, result.transient_calls) == (1, 1, 0)


def test_ac_pass_triggers_transient_with_exact_counts_and_time(
    tmp_path, config, parameters
):
    runner, calls = _fake_stage_runner()
    result = _evaluate(tmp_path, config, parameters, runner)
    assert calls == ["op", "ac", "transient"]
    assert result.evaluation_stage == "fully_feasible"
    assert (result.ngspice_process_calls, result.logical_high_fidelity_calls) == (3, 3)
    assert result.accumulated_ngspice_seconds == pytest.approx(0.6)
    assert result.outer_wall_seconds == pytest.approx(0.66)
    assert result.orchestration_seconds == pytest.approx(0.06)


def test_full_policy_runs_all_stages_even_when_op_fails(tmp_path, config, parameters):
    runner, calls = _fake_stage_runner(op_valid=False)
    result = _evaluate(
        tmp_path, config, parameters, runner, policy="full"
    )
    assert calls == ["op", "ac", "transient"]
    assert result.evaluation_stage == "full_infeasible"
    assert result.ngspice_process_calls == 3


def test_no_synthetic_metric_and_partial_feedback_is_deterministic(
    tmp_path, config, parameters
):
    runner, _ = _fake_stage_runner(op_valid=False)
    result = _evaluate(tmp_path, config, parameters, runner)
    first = hierarchical_objective(
        result.evaluation_stage,
        result.constraint_violation,
        result.metrics,
        ugf_status=result.statuses["ugf_status"],
        phase_margin_status=result.statuses["phase_margin_status"],
        positive_slew_status=result.statuses["positive_slew_status"],
        negative_slew_status=result.statuses["negative_slew_status"],
    )
    second = hierarchical_objective(
        result.evaluation_stage,
        result.constraint_violation,
        result.metrics,
        ugf_status=result.statuses["ugf_status"],
        phase_margin_status=result.statuses["phase_margin_status"],
        positive_slew_status=result.statuses["positive_slew_status"],
        negative_slew_status=result.statuses["negative_slew_status"],
    )
    assert first == second == result.objective_value
    assert set(result.metrics) == set(CANONICAL_METRICS)
    assert result.metrics["dc_gain_db"] is None


def test_feasibility_definition_is_identical_to_task7(tmp_path, config, parameters):
    runner, _ = _fake_stage_runner()
    result = _evaluate(tmp_path, config, parameters, runner)
    task7 = evaluate_task7_objective(
        result.metrics,
        TASK8_SPECIFICATION,
        ugf_status=result.statuses["ugf_status"],
        phase_margin_status=result.statuses["phase_margin_status"],
        positive_slew_status=result.statuses["positive_slew_status"],
        negative_slew_status=result.statuses["negative_slew_status"],
    )
    assert result.is_feasible == task7.is_feasible
    assert result.constraint_violation == task7.constraint_violation


def test_replay_detects_a_counterfactual_false_rejection():
    metrics = {
        "operating_region_valid": 0.0,
        "dc_power_w": 1e-4,
        "output_dc_voltage": 0.9,
        "dc_gain_db": 20.0,
        "ugf_hz": 2e6,
        "ugf_lower_bound_hz": None,
        "phase_margin_deg": 60.0,
        "positive_slew_v_per_s": 2e6,
        "negative_slew_v_per_s": 2e6,
    }
    decision = replay_decision(
        metrics,
        ugf_status="measured",
        phase_margin_status="measured",
        positive_slew_status="measured",
        negative_slew_status="measured",
        full_is_feasible=True,
    )
    assert decision.false_rejection


@pytest.mark.parametrize("boundary", ("op", "ac"))
def test_resume_at_each_stage_boundary(
    tmp_path, config, parameters, boundary
):
    runner, calls = _fake_stage_runner()
    with pytest.raises(StageBoundaryReached):
        _evaluate(
            tmp_path,
            config,
            parameters,
            runner,
            stop_after_stage=boundary,
        )
    before = list(calls)
    result = _evaluate(tmp_path, config, parameters, runner)
    if boundary == "op":
        assert before == ["op"]
        assert calls == ["op", "ac", "transient"]
    else:
        assert before == ["op", "ac"]
        assert calls == ["op", "ac", "transient"]
    assert result.is_feasible


def test_fairness_identity_allows_only_policy_hash_difference(config, tmp_path):
    common = {
        "base_config_path": FROZEN,
        "method": "random",
        "seed": 0,
        "experiment_design": "equal_candidate",
        "output_root": tmp_path,
        "candidate_budget": 50,
    }
    full = fairness_identity(Task8RunDefinition(policy="full", **common), config)
    hierarchical = fairness_identity(
        Task8RunDefinition(policy="hierarchical", **common), config
    )
    differences = {
        key for key in full if full[key] != hierarchical[key]
    }
    assert differences == {"evaluation_policy_hash"}


def _fake_evaluation(policy):
    metrics = {name: None for name in CANONICAL_METRICS}
    metrics.update(
        {
            "dc_power_w": 2e-4,
            "output_dc_voltage": 0.9,
            "operating_region_valid": 1.0,
        }
    )
    return Task8Evaluation(
        policy=policy,
        evaluation_stage="op_rejected",
        first_blocking_constraint="operating_region",
        simulation_status="success",
        metrics=metrics,
        statuses={
            "ugf_status": "not_run",
            "phase_margin_status": "not_run",
            "ugf_crossing_count": 0,
            "positive_slew_status": "not_run",
            "negative_slew_status": "not_run",
        },
        evidence={},
        analysis_errors={"op": None, "ac": None, "transient": None},
        objective_value=3.5,
        constraint_violation=1.0,
        constraint_components={"op_stage": 1.0},
        is_feasible=False,
        ngspice_process_calls=1,
        op_calls=1,
        ac_calls=0,
        transient_calls=0,
        accumulated_ngspice_seconds=0.1,
        outer_wall_seconds=0.11,
        orchestration_seconds=0.01,
        process_elapsed_estimate_count=0,
    )


def test_equal_candidate_and_equal_time_budget_and_overshoot(
    tmp_path, monkeypatch
):
    import circuitpilot.experiments.task8_runner as module

    monkeypatch.setattr(
        module,
        "evaluate_task8_candidate",
        lambda *args, **kwargs: _fake_evaluation(kwargs["policy"]),
    )
    equal_candidate = Task8RunDefinition(
        FROZEN, "random", "hierarchical", 0, "equal_candidate",
        tmp_path / "candidate", candidate_budget=3,
    )
    _, candidate_summary = execute_task8_run(equal_candidate)
    assert candidate_summary["candidate_count"] == 3
    assert candidate_summary["ngspice_process_calls"] == 3

    equal_time = Task8RunDefinition(
        FROZEN, "random", "hierarchical", 0, "equal_simulation_time",
        tmp_path / "time", simulation_time_budget_seconds=0.25, candidate_cap=10,
    )
    _, time_summary = execute_task8_run(equal_time)
    assert time_summary["candidate_count"] == 3
    assert time_summary["accumulated_ngspice_seconds"] == pytest.approx(0.3)
    assert time_summary["budget_overshoot_seconds"] == pytest.approx(0.05)


def test_real_sky130_full_reproduction_and_hierarchical_e2e(tmp_path, config):
    executable = resolve_ngspice_executable(config.ngspice_config.executable)
    if executable is None:
        pytest.skip("ngspice is unavailable")
    if config.circuit_config is None or not config.circuit_config.model.model_library.is_file():
        pytest.skip("frozen SKY130 model library is unavailable")
    best = json.loads(
        (FORMAL / "best_raw_evidence" / "index.json").read_text(encoding="utf-8")
    )[0]
    task7 = evaluate_task7_full_candidate(
        config.circuit_config,
        best["parameters"],
        tmp_path / "task7",
        executable=executable,
        timeout_seconds=config.timeout,
        start_frequency_hz=config.ngspice_config.start_frequency_hz,
        stop_frequency_hz=config.ngspice_config.stop_frequency_hz,
        points_per_decade=config.ngspice_config.points_per_decade,
    )
    task8_full = evaluate_task8_candidate(
        config.circuit_config,
        best["parameters"],
        tmp_path / "task8_full",
        policy="full",
        executable=executable,
        timeout_seconds=config.timeout,
        start_frequency_hz=config.ngspice_config.start_frequency_hz,
        stop_frequency_hz=config.ngspice_config.stop_frequency_hz,
        points_per_decade=config.ngspice_config.points_per_decade,
    )
    for name, value in task7.metrics.items():
        assert task8_full.metrics[name] == pytest.approx(value) if value is not None else task8_full.metrics[name] is None
    task8_hierarchical = evaluate_task8_candidate(
        config.circuit_config,
        best["parameters"],
        tmp_path / "task8_hierarchical",
        policy="hierarchical",
        executable=executable,
        timeout_seconds=config.timeout,
        start_frequency_hz=config.ngspice_config.start_frequency_hz,
        stop_frequency_hz=config.ngspice_config.stop_frequency_hz,
        points_per_decade=config.ngspice_config.points_per_decade,
    )
    assert task8_hierarchical.simulation_status == "success"
    assert task8_hierarchical.evaluation_stage == "fully_feasible"
    assert task8_hierarchical.is_feasible
    assert task8_hierarchical.ngspice_process_calls == 3
