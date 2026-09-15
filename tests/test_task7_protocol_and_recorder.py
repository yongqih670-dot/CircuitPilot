from pathlib import Path

import pytest

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments.task7_recorder import (
    Task7EvaluationRecord,
    Task7Recorder,
)
from circuitpilot.experiments.task7_runner import (
    FROZEN_SPECIFICATION,
    Task7RunDefinition,
)
from circuitpilot.task7_protocol import (
    TASK7_BENCHMARK_HASH,
    TASK7_SEARCH_SPACE_HASH,
    decode_unit_candidate,
    evaluate_task7_objective,
    protocol_family_hash,
)


FROZEN = Path("research/sky130/two_stage_ota/task7_frozen.yaml")


def _metrics(**updates):
    result = {
        "dc_gain_db": 20.0,
        "ugf_hz": 2e6,
        "ugf_lower_bound_hz": None,
        "phase_margin_deg": 60.0,
        "dc_power_w": 2e-4,
        "output_dc_voltage": 0.9,
        "positive_slew_v_per_s": 2e6,
        "negative_slew_v_per_s": 2e6,
        "operating_region_valid": 1.0,
    }
    result.update(updates)
    return result


def _objective(metrics=None, **statuses):
    values = {
        "ugf_status": "measured",
        "phase_margin_status": "measured",
        "positive_slew_status": "measured",
        "negative_slew_status": "measured",
    }
    values.update(statuses)
    return evaluate_task7_objective(
        _metrics() if metrics is None else metrics,
        FROZEN_SPECIFICATION,
        **values,
    )


def test_frozen_benchmark_hash_is_self_consistent():
    config = load_experiment_config(FROZEN)
    assert config.computed_benchmark_hash() == TASK7_BENCHMARK_HASH


def test_frozen_search_hash_is_self_consistent():
    assert load_experiment_config(FROZEN).search_space_sha256() == TASK7_SEARCH_SPACE_HASH


def test_protocol_family_hash_is_stable_sha256():
    value = protocol_family_hash()
    assert value == "3c8cb79cb7ca41cd064ce52c68630dda40f43dd48b2b5c97a902d3553bc980c9"


def test_decode_unit_candidate_lower_endpoint():
    candidate = decode_unit_candidate([0.0] * 12)
    assert candidate["input_pair_width_m"] == pytest.approx(0.84e-6)
    assert candidate["second_load_bias_v"] == pytest.approx(0.25)
    assert candidate["compensation_capacitance_f"] == pytest.approx(0.05e-12)


def test_decode_unit_candidate_upper_endpoint():
    candidate = decode_unit_candidate([1.0] * 12)
    assert candidate["input_pair_width_m"] == pytest.approx(30e-6)
    assert candidate["second_load_bias_v"] == pytest.approx(1.2)
    assert candidate["compensation_capacitance_f"] == pytest.approx(5e-12)


def test_decode_unit_candidate_rejects_out_of_range():
    with pytest.raises(ValueError):
        decode_unit_candidate([0.5] * 11 + [1.1])


def test_objective_is_lexicographically_feasible_and_power_secondary():
    result = _objective()
    assert result.is_feasible
    assert result.constraint_violation == 0
    assert 0 <= result.objective_value < 1


def test_any_hard_constraint_violation_moves_objective_above_one():
    result = _objective(_metrics(dc_gain_db=5.0))
    assert not result.is_feasible
    assert result.constraint_components["gain_min"] > 0
    assert result.objective_value > 1


def test_unmeasured_slew_is_a_hard_violation():
    result = _objective(positive_slew_status="insufficient_transition")
    assert result.constraint_components["positive_slew_min"] == 1
    assert not result.is_feasible


def test_right_censored_ugf_uses_lower_bound_but_pm_remains_unavailable():
    result = _objective(
        _metrics(ugf_hz=None, ugf_lower_bound_hz=1e10, phase_margin_deg=None),
        ugf_status="right_censored",
        phase_margin_status="unavailable",
    )
    assert result.constraint_components["ugf_min"] == 0
    assert result.constraint_components["phase_margin_min"] == 1
    assert not result.is_feasible


def test_lower_feasible_power_has_lower_secondary_objective():
    lower = _objective(_metrics(dc_power_w=1e-4))
    higher = _objective(_metrics(dc_power_w=5e-4))
    assert lower.is_feasible and higher.is_feasible
    assert lower.objective_value < higher.objective_value


def _record(**updates):
    metrics = _metrics()
    objective = _objective(metrics)
    values = {
        "experiment_id": "task7_smoke_random_seed0",
        "run_id": "run-id",
        "experiment_design": "smoke",
        "method": "random",
        "optimizer_phase": "search",
        "seed": 0,
        "iteration": 1,
        "parameters": {"x": 1.0},
        "simulation_status": "success",
        "metrics": metrics,
        "ugf_status": "measured",
        "phase_margin_status": "measured",
        "ugf_crossing_count": 1,
        "positive_slew_status": "measured",
        "negative_slew_status": "measured",
        "operating_region_valid": True,
        "operating_region_mask": 0,
        "operating_region_types": (),
        "device_status": {"input_plus": "saturation"},
        "device_quantities": {"input_plus": {"gm": 1e-3}},
        "analysis_errors": {"op": None, "ac": None, "transient": None},
        "objective_value": objective.objective_value,
        "constraint_violation": objective.constraint_violation,
        "constraint_components": dict(objective.constraint_components),
        "is_feasible": True,
        "event_observed": True,
        "candidate_evaluations": 1,
        "ngspice_process_calls": 3,
        "op_calls": 1,
        "ac_calls": 1,
        "transient_calls": 1,
        "high_fidelity_analysis_calls": 3,
        "screening_calls": 0,
        "op_runtime_seconds": 0.1,
        "ac_runtime_seconds": 0.2,
        "transient_runtime_seconds": 0.3,
        "wall_clock_seconds": 0.6,
        "total_elapsed_time": 0.6,
        "candidate_evaluations_cumulative": 1,
        "ngspice_process_calls_cumulative": 3,
        "op_calls_cumulative": 1,
        "ac_calls_cumulative": 1,
        "transient_calls_cumulative": 1,
        "high_fidelity_analysis_calls_cumulative": 3,
        "screening_calls_cumulative": 0,
        "run_directory": "runs/evaluation_0001",
        "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
        "task7_search_space_hash": TASK7_SEARCH_SPACE_HASH,
        "task7_protocol_family_hash": protocol_family_hash(),
    }
    values.update(updates)
    return Task7EvaluationRecord.now(**values)


def test_recorder_round_trip_preserves_nested_evidence(tmp_path):
    recorder = Task7Recorder(tmp_path)
    recorder.save(_record())
    loaded = recorder.records()
    assert len(loaded) == 1
    assert loaded[0].device_quantities["input_plus"]["gm"] == pytest.approx(1e-3)
    assert (tmp_path / "evaluations.csv").is_file()
    assert (tmp_path / "evaluations.sqlite3").is_file()


def test_record_rejects_any_screening_call():
    with pytest.raises(ValueError):
        _record(screening_calls=1)


def test_record_rejects_non_full_cost_counts():
    with pytest.raises(ValueError):
        _record(ngspice_process_calls=2)


def test_run_definition_identity_changes_with_seed(tmp_path):
    first = Task7RunDefinition(FROZEN, "random", 0, 25, "smoke", tmp_path)
    second = Task7RunDefinition(FROZEN, "random", 1, 25, "smoke", tmp_path)
    assert first.identity_sha256() != second.identity_sha256()


def test_run_definition_resolves_method_without_changing_benchmark(tmp_path):
    definition = Task7RunDefinition(FROZEN, "de", 2, 25, "smoke", tmp_path)
    config = definition.resolved_config()
    assert config.method == "de"
    assert config.seed == 2
    assert config.computed_benchmark_hash() == TASK7_BENCHMARK_HASH
