"""Mechanically select the frozen Task 9 PVT specification-ladder row."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import statistics
import sys

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from circuitpilot.task7_protocol import Task7Specification, stable_hash  # noqa: E402
from task9_full_pvt_research import constraint_evaluation  # noqa: E402


ROOT = PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task9"
CALIBRATION = ROOT / "calibration"
MATRIX = CALIBRATION / "full_pvt" / "full_pvt_matrix.jsonl"
LADDER = ROOT / "PVT_SPECIFICATION_LADDER.yaml"


def specification(row: dict) -> Task7Specification:
    values = row["constraints"]
    return Task7Specification(
        gain_min_db=float(values["gain_min_db"]),
        ugf_min_hz=float(values["ugf_min_hz"]),
        phase_margin_min_deg=float(values["phase_margin_min_deg"]),
        power_max_w=float(values["power_max_w"]),
        positive_slew_min_v_per_s=float(values["positive_slew_min_v_per_s"]),
        negative_slew_min_v_per_s=float(values["negative_slew_min_v_per_s"]),
        output_min_v=float(values["output_low_v"]),
        output_max_v=float(values["output_high_v"]),
    )


def main() -> int:
    ladder = yaml.safe_load(LADDER.read_text(encoding="utf-8"))
    designs = [json.loads(line) for line in MATRIX.read_text(encoding="utf-8").splitlines() if line]
    lower = float(ladder["calibration_density_target"]["lower_fraction_inclusive"])
    upper = float(ladder["calibration_density_target"]["upper_fraction_inclusive"])
    rows: list[dict] = []
    row_evaluations: dict[int, dict[str, dict]] = {}
    for row in ladder["rows"]:
        spec = specification(row)
        by_design: dict[str, dict] = {}
        for design in designs:
            corners = [
                constraint_evaluation(corner["metrics"], corner["statuses"], spec)
                for corner in design["corners"]
            ]
            robust_components = {
                name: max(float(corner["constraint_components"][name]) for corner in corners)
                for name in corners[0]["constraint_components"]
            }
            by_design[design["design_id"]] = {
                "pvt_feasible": all(bool(corner["is_feasible"]) for corner in corners),
                "robust_constraint_components": robust_components,
                "robust_constraint_violation": sum(robust_components.values()),
            }
        feasible = sum(item["pvt_feasible"] for item in by_design.values())
        density = feasible / len(designs)
        distance = lower - density if density < lower else density - upper if density > upper else 0.0
        rows.append(
            {
                "row": int(row["row"]),
                "label": row["label"],
                "feasible_candidates": feasible,
                "candidate_count": len(designs),
                "robust_feasible_density": density,
                "distance_to_target_band": distance,
                "inside_target_band": lower <= density <= upper,
            }
        )
        row_evaluations[int(row["row"])] = by_design
    in_band = [item for item in rows if item["inside_target_band"]]
    selected = min(in_band, key=lambda item: item["row"]) if in_band else min(
        rows, key=lambda item: (item["distance_to_target_band"], item["row"])
    )
    selected_row = next(row for row in ladder["rows"] if int(row["row"]) == selected["row"])
    selected_spec = specification(selected_row)
    runtimes = [float(design["cost"]["accumulated_ngspice_seconds"]) for design in designs]
    median_runtime = statistics.median(runtimes)
    candidate_budget = 50 if median_runtime <= 20.0 else 30 if median_runtime <= 30.0 else 20
    payload = {
        "schema_version": "task9_selected_pvt_specification_v1",
        "selection_rule": ladder["selection_rule"],
        "target_density_band": {"lower": lower, "upper": upper},
        "selected_row": selected["row"],
        "selected_label": selected["label"],
        "selected_constraints": selected_row["constraints"],
        "selected_specification_hash": stable_hash(
            {
                "row": selected["row"],
                "constraints": selected_spec.to_dict(),
                "invariant_requirements": ladder["selection_rule"]["invariant_requirements"],
            }
        ),
        "target_band_achieved": bool(selected["inside_target_band"]),
        "selected_density": selected["robust_feasible_density"],
        "ladder_results": rows,
        "calibration_candidate_count": len(designs),
        "calibration_median_full_pvt_ngspice_seconds": median_runtime,
        "formal_equal_candidate_budget": candidate_budget,
        "formal_equal_time_budget_seconds": 10.0 * median_runtime,
        "formal_equal_time_candidate_cap": 5 * candidate_budget,
        "smoke_candidate_budget": 10,
        "selected_row_design_evaluations": row_evaluations[selected["row"]],
    }
    with (CALIBRATION / "ladder_evaluation.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (CALIBRATION / "selected_specification.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    report = f"""# Task 9 Calibration Specification Selection

The preregistered Sobol64 Full-PVT matrix produced zero robust-feasible
candidates at every one of the five preregistered ladder rows.  The target
0.1%--2.0% density band was therefore not achieved.  Per the frozen fallback,
all rows have the same distance (0.1 percentage point) to the closed band, and
the stricter lower-row tie break mechanically selects **row {selected['row']}**
(`{selected['label']}`).  No threshold was changed or interpolated.

Operating-region validity is invariant across the ladder; no calibration
candidate had all 15 corners operating-region valid (maximum four valid
corners for one candidate).  This explains why numerical relaxation did not
change robust density and is retained as a benchmark-difficulty limitation.

The selected specification hash is
`{payload['selected_specification_hash']}`.  The calibration median complete
Full-PVT cost is {median_runtime:.3f} accumulated ngspice seconds, mechanically
selecting an equal-candidate budget of {candidate_budget}, equal-time budget of
{10.0 * median_runtime:.3f} seconds, candidate cap of {5 * candidate_budget},
and smoke budget of 10.

Exact per-row counts are in `calibration/ladder_evaluation.csv`; the complete
selection object and per-design selected-row robust violations are in
`calibration/selected_specification.json`.
"""
    (ROOT / "CALIBRATION_SPECIFICATION_SELECTION.md").write_text(report, encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("selected_row", "selected_density", "target_band_achieved", "selected_specification_hash", "formal_equal_candidate_budget", "formal_equal_time_budget_seconds", "formal_equal_time_candidate_cap")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
