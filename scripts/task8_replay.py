"""Offline equivalence audit of Task 8 gates over frozen Task 7 evidence."""

from __future__ import annotations

import argparse
import csv
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from circuitpilot.task7_protocol import TASK7_BENCHMARK_HASH
from circuitpilot.task8_protocol import (
    EVALUATION_STAGE_SEMANTICS_HASH,
    evaluation_policy_hash,
    replay_decision,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = (
    PROJECT_ROOT
    / "research"
    / "sky130"
    / "two_stage_ota"
    / "results"
    / "formal"
    / "evaluations.csv"
)
TASK8_ROOT = (
    PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task8"
)
DEFAULT_OUTPUT = TASK8_ROOT / "results" / "replay"


def _byte_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def run_replay(input_csv: Path, output_directory: Path) -> dict[str, Any]:
    stage_counts: Counter[str] = Counter()
    blocker_counts: Counter[str] = Counter()
    false_rows: list[dict[str, Any]] = []
    output_rows: list[dict[str, Any]] = []
    with input_csv.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["task7_benchmark_hash"] != TASK7_BENCHMARK_HASH:
                raise RuntimeError("Task 7 replay input benchmark identity drifted")
            metrics = json.loads(row["metrics"])
            decision = replay_decision(
                metrics,
                ugf_status=row["ugf_status"],
                phase_margin_status=row["phase_margin_status"],
                positive_slew_status=row["positive_slew_status"],
                negative_slew_status=row["negative_slew_status"],
                full_is_feasible=json.loads(row["is_feasible"]),
            )
            stage_counts[decision.evaluation_stage] += 1
            if decision.first_blocking_constraint is not None:
                blocker_counts[decision.first_blocking_constraint] += 1
            output = {
                "experiment_id": row["experiment_id"],
                "method": row["method"],
                "seed": int(row["seed"]),
                "iteration": int(row["iteration"]),
                "task7_is_feasible": json.loads(row["is_feasible"]),
                "replay_stage": decision.evaluation_stage,
                "first_blocking_constraint": decision.first_blocking_constraint,
                "op_calls": decision.op_calls,
                "ac_calls": decision.ac_calls,
                "transient_calls": decision.transient_calls,
                "process_calls": decision.process_calls,
                "false_rejection": decision.false_rejection,
            }
            output_rows.append(output)
            if decision.false_rejection:
                false_rows.append(output)

    output_directory.mkdir(parents=True, exist_ok=True)
    row_path = output_directory / "staged_replay.csv"
    fieldnames = list(output_rows[0]) if output_rows else []
    with row_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)
    summary = {
        "schema_version": 1,
        "mode": "offline_replay_no_ngspice",
        "input_csv": str(input_csv.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "input_csv_sha256": _byte_hash(input_csv),
        "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
        "hierarchical_policy_hash": evaluation_policy_hash("hierarchical"),
        "evaluation_stage_semantics_hash": EVALUATION_STAGE_SEMANTICS_HASH,
        "candidate_count": len(output_rows),
        "stage_counts": dict(sorted(stage_counts.items())),
        "first_blocking_constraint_counts": dict(sorted(blocker_counts.items())),
        "op_rejected": stage_counts["op_rejected"],
        "ac_rejected": stage_counts["ac_rejected"],
        "transient_required": (
            stage_counts["transient_rejected"] + stage_counts["fully_feasible"]
        ),
        "full_feasible_count": sum(row["task7_is_feasible"] for row in output_rows),
        "false_rejection_count": len(false_rows),
        "new_ngspice_process_calls": 0,
    }
    _write_json(output_directory / "summary.json", summary)
    _write_json(output_directory / "false_rejections.json", false_rows)
    return summary


def _write_report(summary: dict[str, Any]) -> None:
    stages = summary["stage_counts"]
    blockers = summary["first_blocking_constraint_counts"]
    report = f"""# Task 8 Offline Replay Equivalence Report

Status: {"PASS" if summary["false_rejection_count"] == 0 else "FAIL"}

This audit replayed the frozen Task 8 staged rules over all
{summary["candidate_count"]} saved Task 7 Full candidates. It launched zero
new ngspice processes and is not counted as a Task 8 simulation experiment.

## Identity

- Task 7 benchmark hash: {summary["task7_benchmark_hash"]}
- Task 7 formal evidence SHA-256: {summary["input_csv_sha256"]}
- Task 8 hierarchical policy hash: {summary["hierarchical_policy_hash"]}
- evaluation-stage semantics hash: {summary["evaluation_stage_semantics_hash"]}

## Replay outcomes

| Outcome | Count |
|---|---:|
| OP rejected | {stages.get("op_rejected", 0)} |
| AC rejected | {stages.get("ac_rejected", 0)} |
| Transient rejected | {stages.get("transient_rejected", 0)} |
| Fully feasible | {stages.get("fully_feasible", 0)} |
| Transient required | {summary["transient_required"]} |
| Task 7 Full feasible | {summary["full_feasible_count"]} |
| False rejection | {summary["false_rejection_count"]} |

## First blocking constraints

| Constraint | Count |
|---|---:|
"""
    for name, count in blockers.items():
        report += f"| {name} | {count} |\n"
    report += f"""
## Gate decision

The required criterion is false_rejection_count == 0. The observed count is
{summary["false_rejection_count"]}; therefore the replay gate
{"passes and Task 8 may proceed to cost profiling" if summary["false_rejection_count"] == 0 else "fails and all new optimizer experiments are prohibited"}.
"""
    (TASK8_ROOT / "REPLAY_EQUIVALENCE_REPORT.md").write_text(
        report, encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    summary = run_replay(args.input.resolve(), args.output.resolve())
    _write_report(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["false_rejection_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
