"""Publish deterministic Task 5 calibration summaries and plots."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import median
from typing import Any

import matplotlib.pyplot as plt
import numpy as np


LADDER = (
    (15.0, 2.0e7, 35.0, 1.0e-3),
    (18.0, 3.0e7, 40.0, 8.0e-4),
    (20.0, 5.0e7, 45.0, 6.0e-4),
    (22.0, 7.5e7, 50.0, 5.0e-4),
    (24.0, 1.0e8, 55.0, 4.0e-4),
    (26.0, 1.5e8, 60.0, 3.0e-4),
    (28.0, 2.0e8, 65.0, 2.5e-4),
    (30.0, 3.0e8, 70.0, 2.0e-4),
)


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "minimum": None,
            "q25": None,
            "median": None,
            "q75": None,
            "maximum": None,
        }
    array = np.asarray(values, dtype=float)
    return {
        "count": len(values),
        "minimum": float(np.min(array)),
        "q25": float(np.quantile(array, 0.25)),
        "median": float(np.median(array)),
        "q75": float(np.quantile(array, 0.75)),
        "maximum": float(np.max(array)),
    }


def publish(source: Path, output_directory: Path) -> dict[str, Any]:
    with source.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    metrics = [json.loads(row["raw_metrics"]) for row in rows]
    if len(rows) != 256:
        raise ValueError(f"Task 5 calibration requires 256 rows, found {len(rows)}")
    process_calls = sum(int(row["ngspice_process_calls"]) for row in rows)
    analysis_calls = sum(int(row["analysis_calls"]) for row in rows)
    if process_calls != 256 or analysis_calls != 512:
        raise ValueError("Task 5 calibration cost accounting is inconsistent")

    exact_bandwidth = [
        float(item["bandwidth_hz"])
        for item in metrics
        if item["bandwidth_hz"] is not None
    ]
    exact_cmrr = [
        float(item["cmrr_db"]) for item in metrics if item["cmrr_db"] is not None
    ]
    ladder_rows = []
    for index, (gain, bandwidth, cmrr, power) in enumerate(LADDER, start=1):
        feasible = sum(
            item["differential_gain_db"] >= gain
            and (
                item["bandwidth_hz"]
                if item["bandwidth_hz"] is not None
                else item["bandwidth_lower_bound_hz"]
            )
            >= bandwidth
            and (
                item["cmrr_db"]
                if item["cmrr_db"] is not None
                else item["cmrr_lower_bound_db"]
            )
            >= cmrr
            and item["dc_power_w"] <= power
            and 0.25 <= item["output_dc_voltage"] <= 1.55
            and item["operating_region_valid"] >= 1.0
            for item in metrics
        )
        ladder_rows.append({
            "row": index,
            "differential_gain_min_db": gain,
            "bandwidth_min_hz": bandwidth,
            "cmrr_min_db": cmrr,
            "power_max_w": power,
            "feasible_candidates": feasible,
            "feasible_fraction": feasible / len(metrics),
        })
    inside = [
        row for row in ladder_rows if 0.005 <= row["feasible_fraction"] <= 0.03
    ]
    pool = inside or ladder_rows
    selected = min(
        pool,
        key=lambda row: (abs(row["feasible_fraction"] - 0.015), -row["row"]),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "calibration_csv": source.as_posix(),
        "candidate_design": {
            "kind": "sobol",
            "count": 256,
            "scramble": False,
            "seed_metadata": 0,
        },
        "candidate_evaluations": len(rows),
        "ngspice_process_calls": process_calls,
        "analysis_calls": analysis_calls,
        "simulation_successes": sum(
            row["simulation_status"] == "success" for row in rows
        ),
        "simulation_failures": sum(
            row["simulation_status"] != "success" for row in rows
        ),
        "bandwidth_status_counts": {
            status: sum(row["bandwidth_status"] == status for row in rows)
            for status in sorted({row["bandwidth_status"] for row in rows})
        },
        "cmrr_status_counts": {
            status: sum(row["cmrr_status"] == status for row in rows)
            for status in sorted({row["cmrr_status"] for row in rows})
        },
        "operating_region_valid_count": sum(
            item["operating_region_valid"] >= 1.0 for item in metrics
        ),
        "distributions": {
            "differential_gain_db": _distribution(
                [float(item["differential_gain_db"]) for item in metrics]
            ),
            "bandwidth_hz_exact": _distribution(exact_bandwidth),
            "cmrr_db_exact": _distribution(exact_cmrr),
            "dc_power_w": _distribution(
                [float(item["dc_power_w"]) for item in metrics]
            ),
            "output_dc_voltage": _distribution(
                [float(item["output_dc_voltage"]) for item in metrics]
            ),
            "tail_current_a": _distribution(
                [float(item["tail_current_a"]) for item in metrics]
            ),
            "candidate_runtime_s": _distribution(
                [float(row["simulation_time"]) for row in rows]
            ),
        },
        "specification_ladder": ladder_rows,
        "selected_specification": selected,
        "target_band_met": bool(inside),
        "formal_budget": (
            50
            if median(float(row["simulation_time"]) for row in rows) > 1.5
            else 100
        ),
    }
    (output_directory / "calibration_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    figure, axes = plt.subplots(2, 3, figsize=(13, 8), constrained_layout=True)
    plots = (
        ("Ad (dB)", [item["differential_gain_db"] for item in metrics]),
        ("Bandwidth (Hz, exact)", exact_bandwidth),
        ("CMRR (dB, exact)", exact_cmrr),
        ("DC power (W)", [item["dc_power_w"] for item in metrics]),
        ("Output DC voltage (V)", [item["output_dc_voltage"] for item in metrics]),
        ("Tail current (A)", [item["tail_current_a"] for item in metrics]),
    )
    for axis, (label, values) in zip(axes.flat, plots):
        axis.hist(values, bins=24, color="#2878B5", alpha=0.85)
        axis.set_xlabel(label)
        axis.set_ylabel("Candidates")
        axis.grid(True, linestyle=":", alpha=0.45)
    figure.suptitle("Task 5 deterministic Sobol calibration distributions")
    figure.savefig(output_directory / "calibration_distributions.png", dpi=160)
    plt.close(figure)

    figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
    axis.bar(
        [row["row"] for row in ladder_rows],
        [100.0 * row["feasible_fraction"] for row in ladder_rows],
        color=["#D9534F" if row["row"] == selected["row"] else "#7AA6C2" for row in ladder_rows],
    )
    axis.axhspan(0.5, 3.0, color="#5CB85C", alpha=0.18, label="target band")
    axis.set_xlabel("Pre-registered ladder row")
    axis.set_ylabel("Feasible candidates (%)")
    axis.set_title("Task 5 calibration feasible density")
    axis.set_xticks(range(1, len(ladder_rows) + 1))
    axis.grid(True, axis="y", linestyle=":", alpha=0.45)
    axis.legend(loc="best")
    figure.savefig(output_directory / "calibration_feasible_density.png", dpi=160)
    plt.close(figure)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = publish(args.csv.resolve(), args.output.resolve())
    print(json.dumps(payload["selected_specification"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
