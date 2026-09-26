"""Scan all locally saved Task 7--9 AC response files for unity crossings."""

from __future__ import annotations

from collections import Counter
import csv
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from circuitpilot.parser import parse_ac_output  # noqa: E402
from circuitpilot.sky130_two_stage_ota import measure_task7_stability  # noqa: E402
from circuitpilot.task9_5_stability import all_unity_crossings, first_and_critical_pm  # noqa: E402


BASE = ROOT / "research/sky130/two_stage_ota"
OUTPUT = BASE / "task9_5/stability"
ROOTS = [
    (ROOT / "research_runs/task7_calibration", "task7", "calibration"),
    (ROOT / "research_runs/task7", "task7", "mixed"),
]
for task in ("task8", "task9"):
    for design in ("smoke", "equal_candidate", "equal_simulation_time"):
        ROOTS.append((BASE / task / "results" / design / "runs", task, design))


def raw_responses():
    for root, task, design in ROOTS:
        if not root.is_dir():
            continue
        filename = "data.dat" if task == "task9" else "ac.dat"
        for directory, _, files in os.walk(root):
            if Path(directory).name == "ac" and filename in files:
                path = Path(directory) / filename
                parts = path.relative_to(root).parts
                resolved_design = design
                if task == "task7" and design == "mixed":
                    resolved_design = "smoke" if "smoke" in parts[0] else "formal"
                run_id = next((part for part in parts if part.startswith("cp-")), "")
                iteration = next((part for part in parts if part.startswith(("evaluation_", "candidate_"))), "")
                corner = next((part for part in parts if "__" in part and
                               part.split("__", 1)[0] in ("tt", "ss", "ff", "fs", "sf")),
                              "tt__nominal")
                yield path, task, resolved_design, run_id, iteration, corner, "shadow_full" in parts


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / "all_ac_crossings.csv"
    fields = (
        "task", "design", "run_id", "iteration", "corner_id", "shadow_full",
        "path", "parsed", "historical_ugf_status", "historical_pm_status",
        "historical_descending_count", "all_crossover_count", "descending_count",
        "ascending_count", "crossover_frequencies_hz", "crossover_directions",
        "phase_margin_each_crossing_deg", "first_descending_pm_deg",
        "critical_descending_pm_deg", "critical_worse_than_first",
        "first_pass_critical_fail_35deg", "error",
    )
    counts = Counter()
    by_task = Counter()
    examples = []
    multiple_candidate_ids = set()
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for path, task, design, run_id, iteration, corner, shadow in raw_responses():
            common = {
                "task": task, "design": design, "run_id": run_id,
                "iteration": iteration, "corner_id": corner,
                "shadow_full": shadow, "path": path.relative_to(ROOT).as_posix(),
            }
            counts["raw_responses"] += 1
            by_task[(task, design, "raw_responses")] += 1
            try:
                response = parse_ac_output(path)
                historical = measure_task7_stability(response)
                crossings = all_unity_crossings(response)
                first, critical = first_and_critical_pm(crossings)
                descending = sum(item.direction == "descending" for item in crossings)
                ascending = len(crossings) - descending
                worse = first is not None and critical is not None and critical < first - 1e-9
                hard_change = (first is not None and critical is not None and
                               first >= 35.0 and critical < 35.0)
                record = {
                    **common, "parsed": True,
                    "historical_ugf_status": historical.ugf_status.value,
                    "historical_pm_status": historical.phase_margin_status.value,
                    "historical_descending_count": historical.crossing_count,
                    "all_crossover_count": len(crossings),
                    "descending_count": descending, "ascending_count": ascending,
                    "crossover_frequencies_hz": json.dumps([x.frequency_hz for x in crossings]),
                    "crossover_directions": json.dumps([x.direction for x in crossings]),
                    "phase_margin_each_crossing_deg": json.dumps([x.phase_margin_deg for x in crossings]),
                    "first_descending_pm_deg": first,
                    "critical_descending_pm_deg": critical,
                    "critical_worse_than_first": worse,
                    "first_pass_critical_fail_35deg": hard_change,
                    "error": "",
                }
                if len(crossings) > 1:
                    counts["multiple_all_crossings_total"] += 1
                    by_task[(task, design, "multiple_all_crossings_total")] += 1
                    multiple_candidate_ids.add((task, design, run_id, iteration))
                if historical.ugf_status.value == "measured":
                    counts["valid_measured_responses"] += 1
                    by_task[(task, design, "valid_measured_responses")] += 1
                    if len(crossings) > 1:
                        counts["multiple_all_crossings"] += 1
                        by_task[(task, design, "multiple_all_crossings")] += 1
                    if descending > 1:
                        counts["multiple_descending_crossings"] += 1
                        by_task[(task, design, "multiple_descending_crossings")] += 1
                    if worse:
                        counts["critical_worse"] += 1
                        by_task[(task, design, "critical_worse")] += 1
                    if hard_change:
                        counts["first_pass_critical_fail_35deg"] += 1
                        by_task[(task, design, "first_pass_critical_fail_35deg")] += 1
                        if len(examples) < 20:
                            examples.append({"path": common["path"], "first_pm": first,
                                             "critical_pm": critical})
                elif len(crossings) > 1:
                    counts["multiple_crossings_not_historically_measured"] += 1
                if historical.crossing_count != descending:
                    counts["descending_count_mismatch_with_historical"] += 1
            except Exception as exc:
                counts["parse_or_measure_errors"] += 1
                record = {**common, "parsed": False, "error": str(exc)}
            writer.writerow(record)
    summary = {
        "schema_version": "task9_5_crossing_audit_v1",
        "counts": dict(counts),
        "candidate_instances_with_multiple_crossings": len(multiple_candidate_ids),
        "by_task_design": {
            "/".join(key): value for key, value in sorted(by_task.items())
        },
        "first_pass_critical_fail_examples": examples,
        "raw_absence": "Task 9 nominal-gap and Sobol calibration retain parsed crossing counts but no AC response waveforms",
    }
    (OUTPUT / "crossing_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
