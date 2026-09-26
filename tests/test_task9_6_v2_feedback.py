"""Corrected-v2 binding and unknown-versus-exact feedback regressions."""

from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from circuitpilot.task9_protocol import CANONICAL_CORNER_ORDER, CORNER_BY_ID, DEFAULT_STATUSES
from circuitpilot.task9_5_benchmark import benchmark_v2_hash
from circuitpilot.task9_5_region import V2_SEMANTICS
from circuitpilot.task9_6_feedback import summarize_v2_robust_feedback
from circuitpilot import task9_6_v2_evaluator


ROOT = Path(__file__).resolve().parents[1]
FULL = (ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/"
        "full_characterization_matrix.json.gz")
BEST = (ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/"
        "refinement_analysis.json")


def _full():
    with gzip.open(FULL, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def _partial():
    full = _full()
    first = deepcopy(full["corners"][0])
    first["completed_analyses"] = ["op"]
    first["constraint_components"] = {
        name: value for name, value in first["constraint_components"].items()
        if name in {"operating_region", "power_max", "output_low", "output_high"}
    }
    first["analysis_errors"] = {"op": None}
    corners = [first]
    for corner_id in CANONICAL_CORNER_ORDER[1:]:
        corners.append({**CORNER_BY_ID[corner_id].to_dict(),
                        "completed_analyses": [], "metrics": None,
                        "statuses": None, "evidence": None,
                        "analysis_errors": None, "application_checks": None,
                        "constraint_components": None})
    return {"benchmark_v2_hash": benchmark_v2_hash(),
            "parameters": full["parameters"], "mode": "hierarchical",
            "process_calls": 1, "complete_full_matrix": False,
            "is_feasible": False, "corners": corners}


def test_complete_real_negative_matrix_has_exact_v2_violation():
    feedback = summarize_v2_robust_feedback(_full())
    assert feedback["robust_evaluation_status"] == "exact"
    assert feedback["final_ranking_eligible"]
    assert feedback["exact_robust_violation"] > 1.0
    assert feedback["measured_analysis_count"] == 45
    assert feedback["passed_complete_corners"] == 12
    assert feedback["unknown_analyses"] == []


def test_early_hierarchy_keeps_44_analyses_unknown_not_zero():
    feedback = summarize_v2_robust_feedback(_partial())
    assert feedback["robust_evaluation_status"] == "partial"
    assert feedback["exact_robust_violation"] is None
    assert len(feedback["unknown_analyses"]) == 44
    assert feedback["measured_constraint_lower_bounds"]["gain_min"] is None
    assert feedback["corner_feedback"][1]["constraint_components"]["power_max"] is None
    assert feedback["partial_search_score"]["eligible"]
    assert not feedback["final_ranking_eligible"]


def test_complete_hierarchical_matrix_is_still_not_exact_full_pvt():
    raw = _full()
    raw["mode"] = "hierarchical"
    raw["complete_full_matrix"] = False
    feedback = summarize_v2_robust_feedback(raw)
    assert feedback["robust_evaluation_status"] == "partial"
    assert feedback["exact_robust_violation"] is None
    assert feedback["measured_analysis_count"] == 45
    assert feedback["unknown_analyses"] == []
    assert not feedback["final_ranking_eligible"]


def test_five_corner_op_only_diagnostic_is_partial():
    raw = _partial()
    raw["mode"] = "op_only"
    raw["corners"][0]["constraint_components"]["operating_region"] = 0.0
    feedback = summarize_v2_robust_feedback(raw)
    assert feedback["robust_evaluation_status"] == "partial"
    assert feedback["exact_robust_violation"] is None
    assert feedback["measured_constraint_lower_bounds"]["gain_min"] is None
    assert len(feedback["unknown_analyses"]) == 44


def test_partial_error_cannot_gain_promotion_by_missing_metrics():
    raw = _partial()
    raw["corners"][0]["analysis_errors"]["op"] = "ngspice failed"
    feedback = summarize_v2_robust_feedback(raw)
    assert feedback["exact_robust_violation"] is None
    assert feedback["partial_search_score"]["eligible"] is False
    assert feedback["measured_constraint_lower_bounds"]["power_max"] is None


def test_reject_old_hash_and_unversioned_region():
    raw = _partial()
    raw["benchmark_v2_hash"] = "ec2d4de0e0c5694598cc7444b4fa9b63a8d8b533fa68bdd504e5262ebd5e2d61"
    with pytest.raises(ValueError, match="corrected Benchmark v2"):
        summarize_v2_robust_feedback(raw)
    raw = _partial()
    raw["corners"][0]["evidence"]["region_semantics"] = "long_channel_proxy_v1"
    with pytest.raises(ValueError, match="non-v2"):
        summarize_v2_robust_feedback(raw)


def test_frozen_bounds_with_explicit_four_ulp_roundoff_record():
    parameters = json.loads(BEST.read_text(encoding="utf-8"))["best_parameters"]
    canonical, roundoff = task9_6_v2_evaluator.canonicalize_v2_parameters(parameters)
    assert canonical["compensation_capacitance_f"] == 5e-12
    assert "compensation_capacitance_f" in roundoff
    parameters["compensation_capacitance_f"] = 5.1e-12
    with pytest.raises(ValueError, match="outside frozen bounds"):
        task9_6_v2_evaluator.canonicalize_v2_parameters(parameters)


def test_task9_6_execution_calls_explicit_task9_5_v2_evaluator(monkeypatch, tmp_path):
    parameters = json.loads(BEST.read_text(encoding="utf-8"))["best_parameters"]
    calls = []

    def fake_v2(**kwargs):
        calls.append(kwargs)
        return _partial()

    monkeypatch.setattr(task9_6_v2_evaluator,
                        "evaluate_task9_5_v2_candidate", fake_v2)
    outcome = task9_6_v2_evaluator.evaluate_task9_6_benchmark_v2_candidate(
        parameters=parameters, evaluation_directory=tmp_path,
        executable="unused", mode="hierarchical")
    assert len(calls) == 1
    assert calls[0]["base_config"].tail_bias_v == 0.72
    assert calls[0]["parameters"]["compensation_capacitance_f"] == 5e-12
    assert outcome["benchmark_v2_hash"] == benchmark_v2_hash()
    assert outcome["robust_feedback"]["region_semantics"] == V2_SEMANTICS
