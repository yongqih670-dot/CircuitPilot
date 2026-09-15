"""Run or resume the pre-registered non-adaptive Task 7 Sobol calibration."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from math import log
from pathlib import Path
from statistics import median
import sys
from time import monotonic
from collections import Counter

from scipy.stats import qmc
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.sky130_two_stage_ota import (
    Sky130TwoStageOtaCircuitConfig,
    evaluate_task7_full_candidate,
)
from circuitpilot.task7_protocol import (
    DIFFICULTY_PROTOCOL_VERSION,
    SEARCH_DIMENSIONS,
    Task7Specification,
    decode_unit_candidate,
    evaluate_task7_objective,
    stable_hash,
)


TASK5_CONFIG = (
    ROOT
    / "research"
    / "sky130"
    / "differential_amplifier"
    / "differential_amplifier_frozen.yaml"
)
LADDER_PATH = (
    ROOT / "research" / "sky130" / "two_stage_ota" / "DIFFICULTY_LADDER.yaml"
)
FIELDS = (
    "iteration",
    "parameters",
    "metrics",
    "ugf_status",
    "phase_margin_status",
    "ugf_crossing_count",
    "positive_slew_status",
    "negative_slew_status",
    "operating_region_valid",
    "operating_region_mask",
    "operating_region_types",
    "device_status",
    "device_quantities",
    "errors",
    "candidate_evaluations",
    "ngspice_process_calls",
    "op_calls",
    "ac_calls",
    "transient_calls",
    "high_fidelity_analysis_calls",
    "op_runtime_seconds",
    "ac_runtime_seconds",
    "transient_runtime_seconds",
    "wall_clock_seconds",
    "timestamp",
)
JSON_FIELDS = {
    "parameters",
    "metrics",
    "operating_region_types",
    "device_status",
    "device_quantities",
    "errors",
}


def circuit_config() -> Sky130TwoStageOtaCircuitConfig:
    base = load_experiment_config(TASK5_CONFIG)
    return Sky130TwoStageOtaCircuitConfig(
        supply_voltage_v=1.8,
        input_common_mode_v=0.9,
        tail_bias_v=0.72,
        load_capacitance_f=1.0e-12,
        temperature_c=27.0,
        transient_low_v=0.8,
        transient_high_v=1.0,
        transient_rise_time_s=1.0e-9,
        transient_fall_time_s=1.0e-9,
        transient_rising_edge_s=0.5e-6,
        transient_falling_edge_s=2.0e-6,
        transient_stop_time_s=4.0e-6,
        transient_max_step_s=2.0e-9,
        transient_edge_exclusion_s=5.0e-9,
        slew_lower_fraction=0.2,
        slew_upper_fraction=0.8,
        model=base.circuit_config.model,
    )


def sobol_candidates() -> tuple[dict[str, float], ...]:
    coordinates = qmc.Sobol(d=len(SEARCH_DIMENSIONS), scramble=False).random_base2(m=9)
    return tuple(decode_unit_candidate(row) for row in coordinates)


def read_rows(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if rows and tuple(rows[0]) != FIELDS:
        raise RuntimeError("existing calibration CSV schema changed")
    decoded: list[dict[str, object]] = []
    for row in rows:
        item: dict[str, object] = dict(row)
        for name in JSON_FIELDS:
            item[name] = json.loads(str(item[name]))
        for name in (
            "iteration",
            "ugf_crossing_count",
            "operating_region_mask",
            "candidate_evaluations",
            "ngspice_process_calls",
            "op_calls",
            "ac_calls",
            "transient_calls",
            "high_fidelity_analysis_calls",
        ):
            item[name] = int(str(item[name]))
        item["operating_region_valid"] = str(item["operating_region_valid"]) == "true"
        decoded.append(item)
    return decoded


def append_row(path: Path, row: dict[str, object]) -> None:
    exists = path.is_file()
    with path.open("a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        encoded = dict(row)
        for name in JSON_FIELDS:
            encoded[name] = json.dumps(
                encoded[name], sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        encoded["operating_region_valid"] = str(
            bool(encoded["operating_region_valid"])
        ).lower()
        writer.writerow(encoded)
        stream.flush()


def load_ladder() -> dict[str, object]:
    loaded = yaml.safe_load(LADDER_PATH.read_text(encoding="utf-8"))
    if loaded["protocol_version"] != DIFFICULTY_PROTOCOL_VERSION:
        raise RuntimeError("difficulty ladder version drifted")
    return loaded


def specification_from_row(row: dict[str, object]) -> Task7Specification:
    return Task7Specification.from_mapping(
        {key: value for key, value in row.items() if key != "row"}
    )


def row_feasible(row: dict[str, object], specification: Task7Specification) -> bool:
    metrics = row["metrics"]
    if not isinstance(metrics, dict):
        return False
    if any(row["errors"].values()):
        return False
    try:
        result = evaluate_task7_objective(
            metrics,
            specification,
            ugf_status=str(row["ugf_status"]),
            phase_margin_status=str(row["phase_margin_status"]),
            positive_slew_status=str(row["positive_slew_status"]),
            negative_slew_status=str(row["negative_slew_status"]),
        )
    except (TypeError, ValueError):
        return False
    return result.is_feasible


def select_ladder(rows: list[dict[str, object]], ladder: dict[str, object]) -> dict[str, object]:
    results: list[dict[str, object]] = []
    for raw in ladder["ladder"]:
        specification = specification_from_row(raw)
        count = sum(row_feasible(row, specification) for row in rows)
        results.append(
            {
                "row": int(raw["row"]),
                "feasible_count": count,
                "sample_count": len(rows),
                "feasible_density": count / len(rows),
                "specification": specification.to_dict(),
            }
        )
    target = ladder["target_feasible_density"]
    eligible = [
        item
        for item in results
        if float(target["minimum"])
        <= float(item["feasible_density"])
        <= float(target["maximum"])
    ]
    if eligible:
        selected = max(eligible, key=lambda item: int(item["row"]))
        reason = "most_stringent_in_target_interval"
    else:
        midpoint = float(target["fallback_geometric_midpoint"])

        def distance(item: dict[str, object]) -> tuple[float, int]:
            density = max(float(item["feasible_density"]), 0.5 / len(rows))
            return (abs(log(density) - log(midpoint)), -int(item["row"]))

        selected = min(results, key=distance)
        reason = "nearest_log_geometric_midpoint_fallback"
    return {"ladder_results": results, "selected": selected, "selection_reason": reason}


def run(output: Path, max_new: int | None) -> None:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "calibration.csv"
    candidates = sobol_candidates()
    existing = read_rows(csv_path)
    if len(existing) > len(candidates):
        raise RuntimeError("calibration CSV is longer than the frozen design")
    for index, row in enumerate(existing):
        if row["parameters"] != candidates[index]:
            raise RuntimeError("resumed calibration candidate sequence drifted")

    config = circuit_config()
    ladder = load_ladder()
    design = {
        "protocol_version": DIFFICULTY_PROTOCOL_VERSION,
        "candidate_count": len(candidates),
        "dimension": len(SEARCH_DIMENSIONS),
        "scramble": False,
        "search_dimensions": SEARCH_DIMENSIONS,
        "candidate_sequence_sha256": stable_hash(candidates),
        "circuit_config": config.to_dict(),
        "ladder_sha256": stable_hash(ladder),
        "optimizer_feedback": "forbidden_and_absent",
    }
    (output / "calibration_design.json").write_text(
        json.dumps(design, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    started = monotonic()
    stop = len(candidates) if max_new is None else min(
        len(candidates), len(existing) + max_new
    )
    for index in range(len(existing), stop):
        parameters = candidates[index]
        evaluation = evaluate_task7_full_candidate(
            config,
            parameters,
            output / "runs" / f"candidate_{index + 1:04d}",
            executable="ngspice",
            timeout_seconds=60.0,
            start_frequency_hz=10.0,
            stop_frequency_hz=1.0e10,
            points_per_decade=30,
        )
        region = evaluation.operating_region
        op = evaluation.operating_point
        row = {
            "iteration": index + 1,
            "parameters": parameters,
            "metrics": dict(evaluation.metrics),
            "ugf_status": evaluation.stability.ugf_status.value,
            "phase_margin_status": evaluation.stability.phase_margin_status.value,
            "ugf_crossing_count": evaluation.stability.crossing_count,
            "positive_slew_status": evaluation.slew.positive_status.value,
            "negative_slew_status": evaluation.slew.negative_status.value,
            "operating_region_valid": False if region is None else region.valid,
            "operating_region_mask": 0 if region is None else region.violation_mask,
            "operating_region_types": [] if region is None else region.violation_types,
            "device_status": {} if region is None else region.device_status,
            "device_quantities": {} if op is None else op.device_quantities,
            "errors": dict(evaluation.errors),
            "candidate_evaluations": evaluation.cost.candidate_evaluations,
            "ngspice_process_calls": evaluation.cost.ngspice_process_calls,
            "op_calls": evaluation.cost.op_calls,
            "ac_calls": evaluation.cost.ac_calls,
            "transient_calls": evaluation.cost.transient_calls,
            "high_fidelity_analysis_calls": evaluation.cost.high_fidelity_analysis_calls,
            "op_runtime_seconds": evaluation.cost.op_runtime_seconds,
            "ac_runtime_seconds": evaluation.cost.ac_runtime_seconds,
            "transient_runtime_seconds": evaluation.cost.transient_runtime_seconds,
            "wall_clock_seconds": evaluation.cost.wall_clock_seconds,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        }
        append_row(csv_path, row)
        if (index + 1) % 16 == 0:
            print(f"calibration {index + 1}/{len(candidates)}", flush=True)

    rows = read_rows(csv_path)
    partial = {
        "completed": len(rows) == len(candidates),
        "completed_candidates": len(rows),
        "candidate_count": len(candidates),
        "new_elapsed_seconds": monotonic() - started,
        "cost_totals": {
            name: sum(int(row[name]) for row in rows)
            for name in (
                "candidate_evaluations",
                "ngspice_process_calls",
                "op_calls",
                "ac_calls",
                "transient_calls",
                "high_fidelity_analysis_calls",
            )
        },
        "status_distributions": {
            "ugf": dict(Counter(str(row["ugf_status"]) for row in rows)),
            "phase_margin": dict(
                Counter(str(row["phase_margin_status"]) for row in rows)
            ),
            "positive_slew": dict(
                Counter(str(row["positive_slew_status"]) for row in rows)
            ),
            "negative_slew": dict(
                Counter(str(row["negative_slew_status"]) for row in rows)
            ),
            "operating_region_valid": dict(
                Counter(str(row["operating_region_valid"]).lower() for row in rows)
            ),
        },
        "analysis_error_counts": dict(
            Counter(
                kind
                for row in rows
                for kind, message in row["errors"].items()
                if message
            )
        ),
        "runtime_medians_seconds": (
            {}
            if not rows
            else {
                "op": median(float(row["op_runtime_seconds"]) for row in rows),
                "ac": median(float(row["ac_runtime_seconds"]) for row in rows),
                "transient": median(
                    float(row["transient_runtime_seconds"]) for row in rows
                ),
                "candidate_wall": median(
                    float(row["wall_clock_seconds"]) for row in rows
                ),
            }
        ),
    }
    if partial["completed"]:
        partial.update(select_ladder(rows, ladder))
    (output / "calibration_summary.json").write_text(
        json.dumps(partial, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(partial, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path("research_runs/task7_calibration")
    )
    parser.add_argument("--max-new", type=int)
    args = parser.parse_args()
    if args.max_new is not None and args.max_new <= 0:
        parser.error("--max-new must be positive")
    run(args.output, args.max_new)


if __name__ == "__main__":
    main()
