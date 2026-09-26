import json
from pathlib import Path

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.task9_6_sensitivity import generate_local_sensitivity_candidates
from circuitpilot.task9_6_v2_evaluator import canonicalize_v2_parameters


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/refinement_analysis.json"
FROZEN = ROOT / "research/sky130/two_stage_ota/task7_frozen.yaml"


def test_all_48_preregistered_proposals_are_distinct_and_within_original_bounds():
    config = load_experiment_config(FROZEN)
    parameters = json.loads(BASELINE.read_text(encoding="utf-8"))["best_parameters"]
    canonical, _ = canonicalize_v2_parameters(parameters)
    rows = generate_local_sensitivity_candidates(canonical, config.search_space)
    assert len(rows) == len({row["parameter_vector_sha256"] for row in rows}) == 48
    assert {row["parameter"] for row in rows} == {p.name for p in config.search_space}
    for row in rows:
        assert all(parameter.contains(row["parameters"][parameter.name])
                   for parameter in config.search_space)
    for name in ("input_pair_length_m", "compensation_capacitance_f"):
        at_upper = [row for row in rows if row["parameter"] == name]
        assert len(at_upper) == 4
        assert all(row["boundary_limited"] and row["normalized_offset"] < 0
                   for row in at_upper)
    assert all(row["coordinate"] == "log" for row in rows
               if row["parameter"] == "compensation_capacitance_f")
