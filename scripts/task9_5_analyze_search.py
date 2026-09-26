"""Summarize measured PVT search bottlenecks without claiming infeasibility proof."""

from __future__ import annotations

from collections import Counter
import argparse
from hashlib import sha256
import json
from pathlib import Path

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.sky130_two_stage_ota import DEVICE_ROLES, PFET_ROLES
from circuitpilot.task9_5_region import V2_SEMANTICS, classify_device


ROOT = Path(__file__).resolve().parents[1]
RUNS = {
    "initial": (ROOT / "research_runs/task9_5_feasibility/run_20260926_a",
                ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/search_analysis.json"),
    "refinement": (ROOT / "research_runs/task9_5_feasibility/refine_20260926_b",
                   ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/refinement_analysis.json"),
}
CONFIG = ROOT / "research/sky130/two_stage_ota/task7_frozen.yaml"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", choices=RUNS, default="initial")
    args = parser.parse_args()
    run, output_path = RUNS[args.run]
    ledger = run / "attempts.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    full_op = [row for row in rows if row["result"]["mode"] == "op_only"
               and sum("op" in corner["completed_analyses"]
                       for corner in row["result"]["corners"]) == 15]
    def passing_op(row):
        return sum(all(value == 0 for value in corner["constraint_components"].values())
                   and not corner["analysis_errors"].get("op")
                   for corner in row["result"]["corners"])

    full_op.sort(key=lambda row: (-passing_op(row),
                                  -row["result"]["op_valid_corner_count"],
                                  row["result"]["op_margin_score"]))
    best = full_op[0]
    result = best["result"]
    failed = []
    device_failures = Counter()
    constraint_failures = Counter()
    for corner in result["corners"]:
        constraints = {name: value for name, value in corner["constraint_components"].items()
                       if value > 0}
        constraint_failures.update(constraints)
        devices = corner["evidence"].get("device_quantities", {})
        failing_devices = {}
        for role in DEVICE_ROLES:
            values = devices.get(role, {})
            status = classify_device(values, version=V2_SEMANTICS,
                                     pfet=role in PFET_ROLES)
            if status != "saturation":
                device_failures[role] += 1
                failing_devices[role] = {
                    "status": status,
                    "on_margin_v": values.get("vgs", 0) - values.get("vth", 0),
                    "vdsat_headroom_v": values.get("vds", 0) - values.get("vdsat", 0),
                    "device_quantities": values,
                }
        if constraints:
            failed.append({"corner_id": corner["corner_id"],
                           "constraints": constraints,
                           "failing_devices": failing_devices,
                           "metrics": corner["metrics"]})
    config = load_experiment_config(CONFIG)
    bound_positions = {}
    for parameter in config.search_space:
        value = result["parameters"][parameter.name]
        bound_positions[parameter.name] = {
            "value": value, "low": parameter.low, "high": parameter.high,
            "at_low_1pct": value <= parameter.low + .01 * (parameter.high - parameter.low),
            "at_high_1pct": value >= parameter.high - .01 * (parameter.high - parameter.low),
        }
    output = {
        "run": str(run.relative_to(ROOT)).replace("\\", "/"),
        "ledger_sha256": sha256(ledger.read_bytes()).hexdigest(),
        "attempts": len(rows),
        "complete_15_corner_op_attempts": len(full_op),
        "full_pvt_verifications": sum(row["result"]["mode"] == "full" for row in rows),
        "best_attempt": best["attempt"],
        "best_origin": best["origin"],
        "best_op_valid_corners": result["op_valid_corner_count"],
        "best_op_all_constraints_passing_corners": passing_op(best),
        "best_op_score": result["op_margin_score"],
        "best_parameters": result["parameters"],
        "bound_positions": bound_positions,
        "failed_corners": failed,
        "device_failure_counts": dict(device_failures),
        "constraint_failure_counts": dict(constraint_failures),
    }
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in output.items()
                      if key not in {"bound_positions", "failed_corners", "best_parameters"}},
                     indent=2))


if __name__ == "__main__":
    main()
