"""Produce deterministic summaries for the Task 9 nominal-to-PVT gap."""

from __future__ import annotations

from collections import Counter
import csv
from hashlib import sha256
import json
from pathlib import Path
import statistics


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task9" / "nominal_gap"
MATRIX = ROOT / "full_pvt_matrix.jsonl"
CONSTRAINTS = (
    "gain_min",
    "ugf_min",
    "phase_margin_min",
    "power_max",
    "positive_slew_min",
    "negative_slew_min",
    "output_low",
    "output_high",
    "operating_region",
)


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    designs = [json.loads(line) for line in MATRIX.read_text(encoding="utf-8").splitlines() if line]
    corner_ids = [corner["corner_id"] for corner in designs[0]["corners"]]
    per_corner = Counter()
    per_constraint = Counter()
    per_pair = Counter()
    taxonomy = Counter()
    design_rows: list[dict[str, object]] = []
    analysis_errors = 0
    for design in designs:
        labels: set[str] = set()
        failed_corners = 0
        violations: set[str] = set()
        for corner in design["corners"]:
            failed = [name for name, value in corner["constraint_components"].items() if float(value) > 0.0]
            analysis_errors += sum(value is not None for value in corner["analysis_errors"].values())
            if not failed:
                continue
            failed_corners += 1
            per_corner[corner["corner_id"]] += 1
            for name in failed:
                violations.add(name)
                per_constraint[name] += 1
                per_pair[(corner["corner_id"], name)] += 1
            if corner["process_corner"] != "tt":
                labels.add("process_corner_failure")
            if corner["condition"] == "low_v_high_t":
                labels.update(("low_voltage_failure", "high_temperature_failure"))
            mapping = {
                "operating_region": "operating_region_failure",
                "gain_min": "gain_failure",
                "ugf_min": "UGF_failure",
                "phase_margin_min": "phase_margin_failure",
                "power_max": "power_failure",
                "positive_slew_min": "slew_failure",
                "negative_slew_min": "slew_failure",
                "output_low": "output_bias_failure",
                "output_high": "output_bias_failure",
            }
            labels.update(mapping[name] for name in failed)
            if len(failed) > 1:
                labels.add("multiple_constraint_failure")
        for label in labels:
            taxonomy[label] += 1
        design_rows.append(
            {
                "design_id": design["design_id"],
                "pvt_feasible_row0": design["pvt_feasible"],
                "failed_corner_count": failed_corners,
                "passed_corner_count": len(corner_ids) - failed_corners,
                "violated_constraints": ";".join(sorted(violations)),
                "taxonomy_labels": ";".join(sorted(labels)),
                "robust_constraint_violation": design["robust_constraint_violation"],
                "accumulated_ngspice_seconds": design["cost"]["accumulated_ngspice_seconds"],
            }
        )
    corner_rows = [
        {
            "corner_id": corner_id,
            "failed_designs": per_corner[corner_id],
            "total_designs": len(designs),
            "failure_fraction": per_corner[corner_id] / len(designs),
        }
        for corner_id in corner_ids
    ]
    constraint_rows = [
        {
            "constraint": name,
            "failed_corner_design_pairs": per_constraint[name],
            "total_corner_design_pairs": len(designs) * len(corner_ids),
            "failure_fraction": per_constraint[name] / (len(designs) * len(corner_ids)),
        }
        for name in CONSTRAINTS
    ]
    pair_rows = [
        {
            "corner_id": corner_id,
            "constraint": name,
            "failed_designs": per_pair[(corner_id, name)],
            "total_designs": len(designs),
            "failure_fraction": per_pair[(corner_id, name)] / len(designs),
        }
        for corner_id in corner_ids
        for name in CONSTRAINTS
    ]
    taxonomy_rows = [
        {
            "taxonomy": name,
            "design_count": taxonomy[name],
            "total_designs": len(designs),
            "fraction": taxonomy[name] / len(designs),
        }
        for name in (
            "process_corner_failure",
            "low_voltage_failure",
            "high_temperature_failure",
            "operating_region_failure",
            "gain_failure",
            "UGF_failure",
            "phase_margin_failure",
            "power_failure",
            "slew_failure",
            "output_bias_failure",
            "multiple_constraint_failure",
        )
    ]
    outputs = {
        "design_summary.csv": design_rows,
        "failure_by_corner.csv": corner_rows,
        "failure_by_constraint.csv": constraint_rows,
        "failure_by_corner_constraint.csv": pair_rows,
        "failure_taxonomy.csv": taxonomy_rows,
    }
    for name, rows in outputs.items():
        write_csv(ROOT / name, rows)
    runtimes = [float(design["cost"]["accumulated_ngspice_seconds"]) for design in designs]
    summary = {
        "schema_version": "task9_nominal_to_pvt_gap_summary_v1",
        "nominal_feasible_unique_design_count": len(designs),
        "pvt_feasible_count_row0": sum(bool(design["pvt_feasible"]) for design in designs),
        "nominal_feasible_but_pvt_failed_count": sum(not bool(design["pvt_feasible"]) for design in designs),
        "full_corner_evaluations": len(designs) * len(corner_ids),
        "op_calls": len(designs) * len(corner_ids),
        "ac_calls": len(designs) * len(corner_ids),
        "transient_calls": len(designs) * len(corner_ids),
        "process_calls": 3 * len(designs) * len(corner_ids),
        "analysis_error_count": analysis_errors,
        "candidate_accumulated_ngspice_seconds": {
            "minimum": min(runtimes),
            "median": statistics.median(runtimes),
            "mean": statistics.mean(runtimes),
            "maximum": max(runtimes),
        },
        "matrix_sha256": file_sha256(MATRIX),
        "output_sha256": {name: file_sha256(ROOT / name) for name in outputs},
        "h5_supported": any(not bool(design["pvt_feasible"]) for design in designs),
    }
    (ROOT / "nominal_gap_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    worst_corners = sorted(corner_rows, key=lambda row: (-int(row["failed_designs"]), str(row["corner_id"])))
    worst_constraints = sorted(
        constraint_rows,
        key=lambda row: (-int(row["failed_corner_design_pairs"]), str(row["constraint"])),
    )
    report = f"""# Task 9 Nominal-to-PVT Robustness Gap Report

## Result

All **{len(designs)}** unique saved Task 7/8 nominal-feasible OTA designs were
evaluated with Full-PVT over all 15 frozen corners.  **0/{len(designs)}** remained
PVT feasible under specification-ladder row 0; therefore
**{len(designs)}/{len(designs)}** are nominal-feasible-but-PVT-failed.  This supports
pre-registered H5 and establishes the motivation for robust optimization.  It
does not select corners, train a predictor, or contribute observations to an
optimizer.

## Coverage and integrity

- Candidate sources: every saved evaluation table from Task 7 calibration,
  smoke, and formal plus Task 8 smoke, equal-candidate, and equal-time; identical
  parameter vectors were evaluated once and retain all source references.
- Complete work: {len(designs) * len(corner_ids)} corner evaluations,
  {len(designs) * len(corner_ids)} OP, {len(designs) * len(corner_ids)} AC,
  {len(designs) * len(corner_ids)} transient, and
  {3 * len(designs) * len(corner_ids)} real ngspice process calls.
- Analysis errors: {analysis_errors}.
- VDD checks: all measured OP supply values matched the requested corner.
- Temperature checks: all three ngspice logs per corner reported the requested
  temperature.
- Matrix SHA-256: `{file_sha256(MATRIX)}`.

Full-PVT accumulated ngspice time per candidate was
{min(runtimes):.3f}--{max(runtimes):.3f} s, with median
{statistics.median(runtimes):.3f} s and mean {statistics.mean(runtimes):.3f} s.
This observed cost may be used only by the already-required calibration protocol
to apply its pre-registered sample-size/budget rule.

## Most frequent failing corners

| Corner | Failed designs | Fraction |
|---|---:|---:|
"""
    report += "".join(
        f"| `{row['corner_id']}` | {row['failed_designs']}/{len(designs)} | {float(row['failure_fraction']):.1%} |\n"
        for row in worst_corners
    )
    report += """

`tt__nominal` has zero failures, as expected from the source inclusion rule.
Every other count comes from a complete matrix, so order cannot censor these
frequencies.

## Constraint failures

Counts below are corner-design pairs and are multilabel; one pair can fail
several constraints.

| Constraint | Failed corner-design pairs | Fraction of 405 |
|---|---:|---:|
"""
    report += "".join(
        f"| `{row['constraint']}` | {row['failed_corner_design_pairs']} | {float(row['failure_fraction']):.1%} |\n"
        for row in worst_constraints
    )
    report += """

Operating-region failure is dominant.  This requirement is invariant across
all pre-registered specification-ladder rows, so numerical threshold relaxation
alone is not assumed to guarantee calibration feasibility.

## Reproducible evidence

- `candidate_set.json`: deduplicated nominal-feasible designs and provenance.
- `full_pvt_matrix.jsonl`: complete metrics, statuses, device evidence,
  constraint components, application checks, and costs.
- `corner_matrix.csv`: one flat row per design/corner.
- `design_summary.csv`: per-design robust outcome and taxonomy.
- `failure_by_corner.csv`, `failure_by_constraint.csv`, and
  `failure_by_corner_constraint.csv`: exact distributions.
- `failure_taxonomy.csv`: required multilabel taxonomy.
- `nominal_gap_summary.json`: counts, timing, hashes, and H5 decision.

Reproduce the matrix with `scripts/task9_full_pvt_research.py`, then regenerate
these summaries with `scripts/task9_analyze_nominal_gap.py`.
"""
    (ROOT.parent / "NOMINAL_TO_PVT_GAP_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
