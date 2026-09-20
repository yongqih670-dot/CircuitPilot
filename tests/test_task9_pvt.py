from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import pytest

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments import task9_evaluator
from circuitpilot.experiments.task9_evaluator import (
    PVTHierarchicalEvaluationPolicy,
    PVTFullEvaluationPolicy,
    StageBoundaryReached,
    StageMeasurement,
    evaluate_task9_candidate,
    execute_real_pvt_stage,
)
from circuitpilot.sky130_pvt import task9_corner_model_paths
from circuitpilot.sky130_two_stage_ota import Sky130TwoStageOtaCircuitConfig
from circuitpilot.task7_protocol import stable_hash
from circuitpilot.task9_protocol import (
    CANONICAL_CORNER_ORDER,
    CORNER_ORDER_HASH,
    CORNER_SUITE_HASH,
    PVT_BENCHMARK_HASH,
    PVT_CORNERS,
    STATIC_WORST_FIRST_ORDER,
    corner_constraint_components,
    partial_feedback,
    replay_complete_matrix,
    robust_objective,
)


ROOT = Path(__file__).resolve().parents[1]
TASK7 = ROOT / "research" / "sky130" / "two_stage_ota" / "task7_frozen.yaml"
PARAMETERS = {
    "compensation_capacitance_f": 5.117253350329411e-13,
    "first_stage_load_length_m": 1.2e-06,
    "first_stage_load_width_m": 8.69545222551006e-06,
    "input_pair_length_m": 1e-06,
    "input_pair_width_m": 8.400000000000007e-07,
    "second_load_bias_v": 0.7678827152106364,
    "second_load_length_m": 1.5e-07,
    "second_load_width_m": 3.0183196407747608e-06,
    "second_stage_length_m": 5.476761491642844e-07,
    "second_stage_width_m": 6e-05,
    "tail_length_m": 1.5e-07,
    "tail_width_m": 4.913586325514552e-06,
}


@pytest.fixture(scope="module")
def ota_config() -> Sky130TwoStageOtaCircuitConfig:
    config = load_experiment_config(TASK7).circuit_config
    assert isinstance(config, Sky130TwoStageOtaCircuitConfig)
    return config


def _good_corner(corner_id: str) -> dict:
    corner = next(item for item in PVT_CORNERS if item.corner_id == corner_id)
    return {
        **corner.to_dict(),
        "started": True,
        "completed_analyses": ["op", "ac", "transient"],
        "metrics": {
            "dc_gain_db": 20.0,
            "ugf_hz": 1.0e6,
            "ugf_lower_bound_hz": None,
            "phase_margin_deg": 60.0,
            "minus_3db_bandwidth_hz": 1.0e4,
            "dc_power_w": 1.0e-4,
            "supply_current_a": 5.0e-5,
            "output_dc_voltage": 0.9,
            "stage1_dc_voltage": 0.8,
            "positive_slew_v_per_s": 1.0e6,
            "negative_slew_v_per_s": 1.0e6,
            "operating_region_valid": 1.0,
        },
        "statuses": {
            "ugf_status": "measured",
            "phase_margin_status": "measured",
            "ugf_crossing_count": 1,
            "positive_slew_status": "measured",
            "negative_slew_status": "measured",
        },
    }


def _measurement(kind: str, corner_id: str, *, fail_op: bool = False) -> StageMeasurement:
    corner = next(item for item in PVT_CORNERS if item.corner_id == corner_id)
    if kind == "op":
        metrics = {
            "dc_power_w": 1.0e-4,
            "supply_current_a": 5.0e-5,
            "output_dc_voltage": 0.9,
            "stage1_dc_voltage": 0.8,
            "operating_region_valid": 0.0 if fail_op else 1.0,
        }
        statuses = {}
        evidence = {"measured_supply_voltage_v": corner.vdd_v}
    elif kind == "ac":
        metrics = {
            "dc_gain_db": 20.0,
            "ugf_hz": 1.0e6,
            "ugf_lower_bound_hz": None,
            "phase_margin_deg": 60.0,
            "minus_3db_bandwidth_hz": 1.0e4,
        }
        statuses = {
            "ugf_status": "measured",
            "phase_margin_status": "measured",
            "ugf_crossing_count": 1,
        }
        evidence = {}
    else:
        metrics = {
            "positive_slew_v_per_s": 1.0e6,
            "negative_slew_v_per_s": 1.0e6,
        }
        statuses = {
            "positive_slew_status": "measured",
            "negative_slew_status": "measured",
        }
        evidence = {}
    return StageMeasurement(
        kind,
        metrics,
        statuses,
        evidence,
        None,
        0.1,
        0.12,
        False,
        corner.temperature_c,
    )


def _evaluate(tmp_path: Path, policy: str, config: Sky130TwoStageOtaCircuitConfig, **kwargs):
    return evaluate_task9_candidate(
        policy=policy,
        base_config=config,
        parameters=PARAMETERS,
        evaluation_directory=tmp_path,
        executable="ngspice",
        timeout_seconds=60.0,
        start_frequency_hz=10.0,
        stop_frequency_hz=1.0e10,
        points_per_decade=30,
        **kwargs,
    )


def test_task7_task8_frozen_bytes_unchanged() -> None:
    task8 = ROOT / "research" / "sky130" / "two_stage_ota" / "task8" / "task8_protocol_manifest.json"
    assert sha256(TASK7.read_bytes()).hexdigest() == "077a42c053dfa59b6deb6e19dbca6cd74bec8122ebcb17998b906a4aa590df28"
    assert sha256(task8.read_bytes()).hexdigest() == "9ca7caf490338683aad3d5ef6f50d87427130e9c3b95c8e3f227d44dc070d053"


def test_real_process_fragments_exist(ota_config: Sky130TwoStageOtaCircuitConfig) -> None:
    hashes = set()
    for process in ("tt", "ss", "ff", "fs", "sf"):
        invariant, nfet, pfet = task9_corner_model_paths(ota_config.model, process)
        assert invariant.is_file() and nfet.is_file() and pfet.is_file()
        hashes.add(sha256(nfet.read_bytes()).hexdigest())
    assert len(hashes) == 5


def test_pvt_hash_sensitivity() -> None:
    payload = [corner.to_dict() for corner in PVT_CORNERS]
    assert stable_hash(payload) == CORNER_SUITE_HASH
    changed = json.loads(json.dumps(payload))
    changed[0]["vdd_v"] = 1.79
    assert stable_hash(changed) != CORNER_SUITE_HASH


def test_every_corner_conjunction_and_worst_aggregation() -> None:
    corners = [_good_corner(corner_id) for corner_id in CANONICAL_CORNER_ORDER]
    good = robust_objective(corners)
    assert good.pvt_feasible
    corners[3]["metrics"]["dc_gain_db"] = 6.0
    failed = robust_objective(corners)
    assert not failed.pvt_feasible
    assert failed.robust_constraint_components["gain_min"] == pytest.approx(0.5)
    assert failed.robust_constraint_violation == pytest.approx(0.5)


def test_partial_feedback_uses_no_unrun_stage_metric() -> None:
    corner = _good_corner(STATIC_WORST_FIRST_ORDER[0])
    corner["completed_analyses"] = ["op"]
    corner["metrics"]["dc_gain_db"] = None
    corner["metrics"]["ugf_hz"] = None
    corner["metrics"]["phase_margin_deg"] = None
    corner["metrics"]["positive_slew_v_per_s"] = None
    corner["metrics"]["negative_slew_v_per_s"] = None
    feedback = partial_feedback([corner], progress_units=1)
    assert feedback.partial_constraint_components["gain_min"] == 0.0
    assert feedback.partial_constraint_components["positive_slew_min"] == 0.0


def test_full_policy_evaluates_every_corner(monkeypatch, tmp_path, ota_config) -> None:
    calls = []

    def fake(kind, *, corner_id, **kwargs):
        calls.append((corner_id, kind))
        return _measurement(kind, corner_id)

    monkeypatch.setattr(task9_evaluator, "execute_real_pvt_stage", fake)
    result = _evaluate(tmp_path, "full", ota_config)
    assert isinstance(PVTFullEvaluationPolicy(), PVTFullEvaluationPolicy)
    assert result.is_feasible
    assert result.corners_started == 15
    assert result.corners_completed == 15
    assert result.process_calls == 45
    assert result.op_calls == result.ac_calls == result.transient_calls == 15
    assert len(calls) == 45


def test_hierarchy_stops_and_unknown_metrics_stay_null(monkeypatch, tmp_path, ota_config) -> None:
    calls = []

    def fake(kind, *, corner_id, **kwargs):
        calls.append((corner_id, kind))
        return _measurement(kind, corner_id, fail_op=True)

    monkeypatch.setattr(task9_evaluator, "execute_real_pvt_stage", fake)
    result = _evaluate(tmp_path, "hierarchical", ota_config)
    assert isinstance(PVTHierarchicalEvaluationPolicy(), PVTHierarchicalEvaluationPolicy)
    assert not result.is_feasible
    assert result.first_failing_corner == STATIC_WORST_FIRST_ORDER[0]
    assert result.first_failing_stage == "op"
    assert result.process_calls == result.op_calls == result.corners_started == 1
    assert result.ac_calls == result.transient_calls == 0
    untouched = next(item for item in result.corner_results if item["corner_id"] == STATIC_WORST_FIRST_ORDER[1])
    assert not untouched["started"]
    assert all(value is None for value in untouched["metrics"].values())
    assert all(value is None for value in untouched["constraint_components"].values())
    assert calls == [(STATIC_WORST_FIRST_ORDER[0], "op")]


def test_resume_between_corner_stages(monkeypatch, tmp_path, ota_config) -> None:
    calls = []

    def fake(kind, *, corner_id, **kwargs):
        calls.append((corner_id, kind))
        return _measurement(kind, corner_id)

    monkeypatch.setattr(task9_evaluator, "execute_real_pvt_stage", fake)
    with pytest.raises(StageBoundaryReached):
        _evaluate(tmp_path, "full", ota_config, interrupt_after_stage=7)
    result = _evaluate(tmp_path, "full", ota_config)
    assert result.is_feasible
    assert len(calls) == 45


def test_equal_time_budget_stops_after_completed_analysis(monkeypatch, tmp_path, ota_config) -> None:
    calls = []

    def fake(kind, *, corner_id, **kwargs):
        calls.append((corner_id, kind))
        return _measurement(kind, corner_id)

    monkeypatch.setattr(task9_evaluator, "execute_real_pvt_stage", fake)
    result = _evaluate(
        tmp_path,
        "full",
        ota_config,
        stop_after_accumulated_ngspice_seconds=0.05,
    )
    assert result.simulation_status == "budget_exhausted"
    assert result.evaluation_stage == "budget_exhausted"
    assert result.process_calls == result.op_calls == 1
    assert result.ac_calls == result.transient_calls == 0
    assert calls == [(CANONICAL_CORNER_ORDER[0], "op")]
    resumed = _evaluate(tmp_path, "full", ota_config)
    assert resumed.simulation_status == "budget_exhausted"
    assert calls == [(CANONICAL_CORNER_ORDER[0], "op")]


def test_corner_order_deterministic_and_hash_bound() -> None:
    assert len(STATIC_WORST_FIRST_ORDER) == len(set(STATIC_WORST_FIRST_ORDER)) == 15
    assert set(STATIC_WORST_FIRST_ORDER) == set(CANONICAL_CORNER_ORDER)
    manifest = json.loads(
        (ROOT / "research" / "sky130" / "two_stage_ota" / "task9" / "task9_protocol_manifest.json").read_text()
    )
    assert manifest["hashes"]["corner_order_hash"] == CORNER_ORDER_HASH
    assert manifest["hashes"]["pvt_benchmark_hash"] == PVT_BENCHMARK_HASH


def test_replay_identity_and_false_accept_reject_detection() -> None:
    corners = [_good_corner(corner_id) for corner_id in CANONICAL_CORNER_ORDER]
    identity = replay_complete_matrix(
        corners, order=STATIC_WORST_FIRST_ORDER, full_pvt_feasible=True
    )
    assert identity.replay_pvt_feasible and not identity.false_rejection
    false_accept = replay_complete_matrix(
        corners, order=STATIC_WORST_FIRST_ORDER, full_pvt_feasible=False
    )
    assert false_accept.false_acceptance
    corners[0]["metrics"]["operating_region_valid"] = 0.0
    false_reject = replay_complete_matrix(
        corners, order=STATIC_WORST_FIRST_ORDER, full_pvt_feasible=True
    )
    assert false_reject.false_rejection


def test_real_vdd_temperature_and_multicorner_ota_e2e(tmp_path, ota_config) -> None:
    op = execute_real_pvt_stage(
        "op",
        base_config=ota_config,
        corner_id="ss__low_v_high_t",
        parameters=PARAMETERS,
        directory=tmp_path / "probe",
        executable="ngspice",
        timeout_seconds=60.0,
        start_frequency_hz=10.0,
        stop_frequency_hz=1.0e10,
        points_per_decade=30,
    )
    assert op.error is None
    assert op.evidence["measured_supply_voltage_v"] == pytest.approx(1.62)
    assert op.reported_temperature_c == pytest.approx(125.0)
    result = _evaluate(tmp_path / "full", "full", ota_config)
    assert result.process_calls == 45
    assert result.corners_started == result.corners_completed == 15
    assert not any(
        error
        for corner in result.corner_results
        for error in corner["analysis_errors"].values()
    )
    assert all(
        corner["application_checks"]["vdd_applied"]
        and corner["application_checks"]["temperature_applied_all_completed_stages"]
        for corner in result.corner_results
    )
    assert {corner["process_corner"] for corner in result.corner_results} == {"tt", "ss", "ff", "fs", "sf"}
