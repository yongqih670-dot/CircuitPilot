"""Pre-formal fixed-candidate analysis cost profile for Research Task 8."""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from math import floor
import os
from pathlib import Path
from statistics import mean, median
from time import monotonic
from typing import Any, Iterable

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.simulator import run_ngspice
from circuitpilot.sky130_common_source import sky130_runtime_paths
from circuitpilot.sky130_two_stage_ota import (
    generate_task7_ac_netlist,
    generate_task7_op_netlist,
    generate_task7_transient_netlist,
)
from circuitpilot.task7_protocol import TASK7_BENCHMARK_HASH


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FROZEN_CONFIG = (
    PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task7_frozen.yaml"
)
FORMAL_CSV = (
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
DEFAULT_OUTPUT = TASK8_ROOT / "results" / "cost_profile"
MODES = {
    "op_only": ("op",),
    "op_ac": ("op", "ac"),
    "full": ("op", "ac", "transient"),
}


def _byte_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _quantile(values: Iterable[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("quantile requires at least one value")
    position = (len(ordered) - 1) * probability
    lower = floor(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _statistics(values: Iterable[float]) -> dict[str, float]:
    data = [float(value) for value in values]
    q1 = _quantile(data, 0.25)
    q3 = _quantile(data, 0.75)
    return {
        "count": len(data),
        "median": median(data),
        "mean": mean(data),
        "q1": q1,
        "q3": q3,
        "iqr": q3 - q1,
    }


def _fixed_candidates() -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    with FORMAL_CSV.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if (
                row["experiment_design"] == "formal"
                and row["method"] == "random"
                and int(row["seed"]) == 0
            ):
                selected.append(
                    {
                        "experiment_id": row["experiment_id"],
                        "iteration": int(row["iteration"]),
                        "parameters": json.loads(row["parameters"]),
                    }
                )
                if len(selected) == 16:
                    break
    if [row["iteration"] for row in selected] != list(range(1, 17)):
        raise RuntimeError("pre-registered cost-profile candidate set is unavailable")
    return selected


def _run_analysis(
    kind: str,
    *,
    config: Any,
    parameters: dict[str, float],
    directory: Path,
    timeout_seconds: float,
) -> float:
    directory.mkdir(parents=True, exist_ok=True)
    with sky130_runtime_paths(config.circuit_config.model, directory) as paths:
        windows_runtime = os.name == "nt"
        runtime_data = Path(paths.runtime_ac) if windows_runtime else paths.ac_path
        runtime_op = Path(paths.runtime_op) if windows_runtime else paths.op_path
        runtime_device = (
            Path(paths.runtime_device) if windows_runtime else paths.device_path
        )
        for output in (
            runtime_data,
            runtime_op,
            runtime_device,
            paths.runtime_log,
        ):
            output.unlink(missing_ok=True)
        common = {
            "invariant_path": paths.runtime_invariant,
            "nfet_corner_path": paths.runtime_corner,
            "pfet_corner_path": paths.runtime_pfet_corner,
        }
        if kind == "op":
            text = generate_task7_op_netlist(
                config.circuit_config,
                parameters,
                **common,
                op_output_path=paths.runtime_op,
                device_op_output_path=paths.runtime_device,
            )
        elif kind == "ac":
            text = generate_task7_ac_netlist(
                config.circuit_config,
                parameters,
                **common,
                ac_output_path=paths.runtime_ac,
                start_frequency_hz=config.ngspice_config.start_frequency_hz,
                stop_frequency_hz=config.ngspice_config.stop_frequency_hz,
                points_per_decade=config.ngspice_config.points_per_decade,
            )
        elif kind == "transient":
            text = generate_task7_transient_netlist(
                config.circuit_config,
                parameters,
                **common,
                transient_output_path=paths.runtime_ac,
            )
        else:
            raise ValueError(f"unknown analysis kind '{kind}'")
        Path(paths.runtime_netlist).write_text(text, encoding="utf-8")
        process = run_ngspice(
            paths.runtime_netlist,
            executable=config.ngspice_config.executable,
            timeout_seconds=timeout_seconds,
            log_path=paths.runtime_log,
            preserve_runtime_paths=True,
        )
        return process.elapsed_seconds


def run_profile(output_directory: Path, timeout_seconds: float) -> dict[str, Any]:
    config = load_experiment_config(FROZEN_CONFIG)
    if config.computed_benchmark_hash() != TASK7_BENCHMARK_HASH:
        raise RuntimeError("Task 7 benchmark hash drifted before cost profiling")
    output_directory.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for candidate in _fixed_candidates():
        for mode, analyses in MODES.items():
            started = monotonic()
            elapsed = {"op": 0.0, "ac": 0.0, "transient": 0.0}
            for kind in analyses:
                elapsed[kind] = _run_analysis(
                    kind,
                    config=config,
                    parameters=candidate["parameters"],
                    directory=(
                        output_directory
                        / "runs"
                        / f"candidate_{candidate['iteration']:02d}"
                        / mode
                        / kind
                    ),
                    timeout_seconds=timeout_seconds,
                )
            outer = monotonic() - started
            accumulated = sum(elapsed.values())
            rows.append(
                {
                    "source_experiment_id": candidate["experiment_id"],
                    "source_iteration": candidate["iteration"],
                    "mode": mode,
                    "parameters": json.dumps(
                        candidate["parameters"],
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    "op_calls": int("op" in analyses),
                    "ac_calls": int("ac" in analyses),
                    "transient_calls": int("transient" in analyses),
                    "ngspice_process_calls": len(analyses),
                    "op_subprocess_seconds": elapsed["op"],
                    "ac_subprocess_seconds": elapsed["ac"],
                    "transient_subprocess_seconds": elapsed["transient"],
                    "accumulated_ngspice_seconds": accumulated,
                    "outer_wall_seconds": outer,
                    "orchestration_seconds": max(0.0, outer - accumulated),
                }
            )

    csv_path = output_directory / "cost_profile.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    by_mode: dict[str, Any] = {}
    for mode in MODES:
        matching = [row for row in rows if row["mode"] == mode]
        by_mode[mode] = {
            "accumulated_ngspice_seconds": _statistics(
                row["accumulated_ngspice_seconds"] for row in matching
            ),
            "outer_wall_seconds": _statistics(
                row["outer_wall_seconds"] for row in matching
            ),
            "orchestration_seconds": _statistics(
                row["orchestration_seconds"] for row in matching
            ),
        }
    summary = {
        "schema_version": 1,
        "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
        "task7_formal_csv_sha256": _byte_hash(FORMAL_CSV),
        "fixed_candidate_definition": "Task 7 formal Random seed 0 iterations 1-16",
        "candidate_count": 16,
        "measurement_count": len(rows),
        "new_ngspice_process_calls": sum(
            int(row["ngspice_process_calls"]) for row in rows
        ),
        "statistics": by_mode,
    }
    (output_directory / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return summary


def _write_report(summary: dict[str, Any]) -> None:
    report = """# Task 8 Analysis Cost Profile

Status: completed before Task 8 protocol freeze and formal experiments.

The fixed set is Task 7 formal Random seed 0, iterations 1–16. Every candidate
was re-run as OP-only, OP+AC, and Full OP+AC+transient. These measurements are
instrumentation-only and were not supplied to an optimizer.

## Identity

"""
    report += f"- Task 7 benchmark hash: {summary['task7_benchmark_hash']}\n"
    report += (
        f"- Task 7 formal evidence SHA-256: {summary['task7_formal_csv_sha256']}\n"
    )
    report += f"- new ngspice processes: {summary['new_ngspice_process_calls']}\n"
    report += "\n## Measured costs\n\n"
    report += (
        "| Mode | Metric | Median (s) | Mean (s) | Q1 (s) | Q3 (s) | IQR (s) |\n"
        "|---|---|---:|---:|---:|---:|---:|\n"
    )
    for mode, metrics in summary["statistics"].items():
        for metric, values in metrics.items():
            report += (
                f"| {mode} | {metric} | {values['median']:.6f} | "
                f"{values['mean']:.6f} | {values['q1']:.6f} | "
                f"{values['q3']:.6f} | {values['iqr']:.6f} |\n"
            )
    full = summary["statistics"]["full"]["accumulated_ngspice_seconds"]["median"]
    op = summary["statistics"]["op_only"]["accumulated_ngspice_seconds"]["median"]
    op_ac = summary["statistics"]["op_ac"]["accumulated_ngspice_seconds"]["median"]
    report += f"""
## Check

Median accumulated subprocess time increases from OP-only ({op:.6f} s) to
OP+AC ({op_ac:.6f} s) to Full ({full:.6f} s). The expected Task 7 analysis
cost ordering is therefore present in the Task 8 environment.
"""
    (TASK8_ROOT / "ANALYSIS_COST_PROFILE.md").write_text(
        report, encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    summary = run_profile(args.output.resolve(), args.timeout)
    _write_report(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
