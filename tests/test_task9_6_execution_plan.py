import json
from pathlib import Path

from circuitpilot.task9_6_v2_evaluator import APPROVED_BENCHMARK_V2_HASH


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "research/sky130/two_stage_ota/task9_6/execution_plan.json"
NEAR = ROOT / "research/sky130/two_stage_ota/task9_6/near_corner_selection.json"
PROPOSALS = ROOT / "research/sky130/two_stage_ota/task9_6/sensitivity_candidates.json"


def test_phase_b_budget_is_finite_self_consistent_and_not_approved():
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    near = json.loads(NEAR.read_text(encoding="utf-8"))
    proposals = json.loads(PROPOSALS.read_text(encoding="utf-8"))
    assert plan["phase_b_approved"] is False
    assert plan["benchmark_v2_hash"] == APPROVED_BENCHMARK_V2_HASH
    assert sum(plan["activity_process_allocations"].values()) == 6445
    assert plan["allocated_maximum_ngspice_processes"] == 6445
    assert plan["global_limits"]["maximum_ngspice_processes"] == 6500
    assert plan["allocated_maximum_ngspice_processes"] <= plan["global_limits"]["maximum_ngspice_processes"]
    assert sum(method["candidates"] for method in plan["search_methods"].values()) == 96
    assert plan["sensitivity_candidate_count"] == proposals["candidate_count"] == 48
    assert plan["near_constraint_corner_count"] == len(near["selected_corner_ids"]) == 5
    assert plan["auto_extend_budget"] is False
