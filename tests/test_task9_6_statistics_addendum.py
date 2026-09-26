import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "research/sky130/two_stage_ota/task9_5/statistics/corrected_rmst.csv"


def _row(method, policy, axis):
    with TABLE.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return next(row for row in rows if row["task"] == "task6"
                and row["design"] == "formal_equal_cost"
                and row["method"] == method and row["policy"] == policy
                and row["axis"] == axis)


def test_task6_true_candidate_extrapolation_vs_common_ac_truncation():
    full_candidates = _row("bo", "full", "candidate_count")
    assert (float(full_candidates["group_max_observed"]),
            float(full_candidates["old_horizon"])) == (100.0, 300.0)

    full_ac = _row("pooled", "full", "expensive_ac_calls")
    screened_ac = _row("pooled", "op_screened", "expensive_ac_calls")
    assert float(full_ac["group_max_observed"]) == 200.0
    assert float(screened_ac["group_max_observed"]) == 92.0
    assert float(full_ac["common_supported_horizon"]) == 92.0
    assert float(screened_ac["common_supported_horizon"]) == 92.0
    assert round(float(full_ac["corrected_rmst"]), 3) == 76.100
    assert round(float(screened_ac["corrected_rmst"]), 3) == 34.742
