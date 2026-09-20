"""Derive the pre-registered static Task 9 worst-first corner order."""

from __future__ import annotations

from collections import Counter
import csv
import json
from pathlib import Path
import statistics
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from circuitpilot.task7_protocol import stable_hash  # noqa: E402


ROOT = PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task9"
CALIBRATION = ROOT / "calibration"
MATRIX = CALIBRATION / "full_pvt" / "full_pvt_matrix.jsonl"
SELECTED = CALIBRATION / "selected_specification.json"
NOMINAL_FIRST_ORDER = (
    "tt__nominal",
    "ss__nominal",
    "ff__nominal",
    "fs__nominal",
    "sf__nominal",
    "tt__low_v_high_t",
    "ss__low_v_high_t",
    "ff__low_v_high_t",
    "fs__low_v_high_t",
    "sf__low_v_high_t",
    "tt__high_v_low_t",
    "ss__high_v_low_t",
    "ff__high_v_low_t",
    "fs__high_v_low_t",
    "sf__high_v_low_t",
)
ORDER_RULE = (
    "rejection_fraction_desc",
    "mean_total_normalized_corner_violation_desc",
    "mean_complete_corner_ngspice_seconds_asc",
    "nominal_first_rank_asc",
    "corner_id_asc",
)


def main() -> int:
    designs = [json.loads(line) for line in MATRIX.read_text(encoding="utf-8").splitlines() if line]
    selected = json.loads(SELECTED.read_text(encoding="utf-8"))
    if selected["selected_row"] != 0:
        raise RuntimeError("matrix constraint components are row 0 but a different row was selected")
    by_corner = {
        corner_id: [
            next(corner for corner in design["corners"] if corner["corner_id"] == corner_id)
            for design in designs
        ]
        for corner_id in NOMINAL_FIRST_ORDER
    }
    rows: list[dict[str, object]] = []
    constraint_rows: list[dict[str, object]] = []
    for nominal_rank, corner_id in enumerate(NOMINAL_FIRST_ORDER):
        corners = by_corner[corner_id]
        violations = [float(corner["constraint_violation"]) for corner in corners]
        runtimes = [float(corner["cost"]["accumulated_ngspice_seconds"]) for corner in corners]
        rejected = sum(value > 0.0 for value in violations)
        row = {
            "corner_id": corner_id,
            "process_corner": corners[0]["process_corner"],
            "condition": corners[0]["condition"],
            "vdd_v": corners[0]["vdd_v"],
            "temperature_c": corners[0]["temperature_c"],
            "rejected_candidates": rejected,
            "candidate_count": len(designs),
            "rejection_fraction": rejected / len(designs),
            "mean_total_normalized_corner_violation": statistics.mean(violations),
            "median_total_normalized_corner_violation": statistics.median(violations),
            "mean_complete_corner_ngspice_seconds": statistics.mean(runtimes),
            "median_complete_corner_ngspice_seconds": statistics.median(runtimes),
            "total_complete_corner_ngspice_seconds": sum(runtimes),
            "mean_op_ngspice_seconds": statistics.mean(float(c["cost"]["per_stage_ngspice_seconds"]["op"]) for c in corners),
            "mean_ac_ngspice_seconds": statistics.mean(float(c["cost"]["per_stage_ngspice_seconds"]["ac"]) for c in corners),
            "mean_transient_ngspice_seconds": statistics.mean(float(c["cost"]["per_stage_ngspice_seconds"]["transient"]) for c in corners),
            "nominal_first_rank": nominal_rank,
        }
        rows.append(row)
        for name in corners[0]["constraint_components"]:
            count = sum(float(corner["constraint_components"][name]) > 0.0 for corner in corners)
            constraint_rows.append(
                {
                    "corner_id": corner_id,
                    "constraint": name,
                    "failed_candidates": count,
                    "candidate_count": len(designs),
                    "failure_fraction": count / len(designs),
                    "mean_normalized_violation": statistics.mean(
                        float(corner["constraint_components"][name]) for corner in corners
                    ),
                }
            )
    ordered = sorted(
        rows,
        key=lambda row: (
            -float(row["rejection_fraction"]),
            -float(row["mean_total_normalized_corner_violation"]),
            float(row["mean_complete_corner_ngspice_seconds"]),
            int(row["nominal_first_rank"]),
            str(row["corner_id"]),
        ),
    )
    order = [str(row["corner_id"]) for row in ordered]
    first_failure = Counter()
    for design in designs:
        corners = {corner["corner_id"]: corner for corner in design["corners"]}
        failure = next(
            (corner_id for corner_id in NOMINAL_FIRST_ORDER if not corners[corner_id]["is_feasible"]),
            "pvt_feasible",
        )
        first_failure[failure] += 1
    first_rows = [
        {
            "outcome": outcome,
            "count": first_failure[outcome],
            "candidate_count": len(designs),
            "probability": first_failure[outcome] / len(designs),
        }
        for outcome in (*NOMINAL_FIRST_ORDER, "pvt_feasible")
    ]
    for name, output_rows in (
        ("corner_difficulty.csv", rows),
        ("corner_constraint_failures.csv", constraint_rows),
        ("nominal_first_failure_distribution.csv", first_rows),
    ):
        with (CALIBRATION / name).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(output_rows[0]))
            writer.writeheader()
            writer.writerows(output_rows)
    identity = {
        "schema_version": "task9_static_worst_first_order_v1",
        "selected_specification_hash": selected["selected_specification_hash"],
        "calibration_candidate_set_hash": json.loads(
            (CALIBRATION / "calibration_candidates.json").read_text(encoding="utf-8")
        )["candidate_set_hash"],
        "order_rule": list(ORDER_RULE),
        "static_worst_first_order": order,
    }
    payload = {
        **identity,
        "corner_order_hash": stable_hash(identity),
        "nominal_first_order": list(NOMINAL_FIRST_ORDER),
        "ordered_statistics": ordered,
    }
    (CALIBRATION / "static_corner_order.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    table = "\n".join(
        f"| {index + 1} | `{row['corner_id']}` | {float(row['rejection_fraction']):.1%} | "
        f"{float(row['mean_total_normalized_corner_violation']):.6f} | "
        f"{float(row['mean_complete_corner_ngspice_seconds']):.3f} |"
        for index, row in enumerate(ordered)
    )
    report = f"""# Task 9 Static Corner Order

The pre-registered lexicographic rule was applied once to the completed Sobol64
Full-PVT matrix under selected specification row 0.  The frozen formal order is:

```text
{', '.join(order)}
```

Corner-order SHA-256: `{payload['corner_order_hash']}`.

| Rank | Corner | Rejection fraction | Mean normalized violation | Mean complete-corner ngspice s |
|---:|---|---:|---:|---:|
{table}

The order is static for every later candidate and is not an adaptive corner
predictor.  Exact unrounded sort inputs are stored in
`calibration/static_corner_order.json`; component failures, runtime fields, and
nominal-first first-failure probabilities are retained in the companion CSVs.
"""
    (ROOT / "STATIC_CORNER_ORDER.md").write_text(report, encoding="utf-8")
    print(json.dumps({"static_worst_first_order": order, "corner_order_hash": payload["corner_order_hash"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
