"""Publish compact, auditable Task 7 smoke/formal evidence and detailed summaries."""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
import shutil
from statistics import mean, median, quantiles
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from circuitpilot.experiments.config import experiment_config_from_mapping
from circuitpilot.experiments.task7_batch import (
    load_evaluations,
    load_summary,
    validate_fairness,
    write_statistics,
)
from circuitpilot.experiments.task7_recorder import TASK7_COLUMNS
from circuitpilot.task7_protocol import (
    METHODS,
    TASK7_BENCHMARK_HASH,
    TASK7_COMPONENT_HASHES,
    TASK7_SEARCH_SPACE_HASH,
    protocol_family_hash,
    task7_component_hashes,
)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "minimum": None,
            "q1": None,
            "median": None,
            "mean": None,
            "q3": None,
            "iqr": None,
            "maximum": None,
        }
    q1, _, q3 = quantiles(values, n=4, method="inclusive")
    return {
        "count": len(values),
        "minimum": min(values),
        "q1": q1,
        "median": median(values),
        "mean": mean(values),
        "q3": q3,
        "iqr": q3 - q1,
        "maximum": max(values),
    }


def _stability_status(row: dict[str, Any]) -> str:
    if row["ugf_status"] == "invalid_response":
        return "invalid_response"
    if row["ugf_status"] != "measured":
        return "no_valid_unity_crossing"
    value = row["metrics"].get("phase_margin_deg")
    if row["phase_margin_status"] != "measured" or value is None:
        return "invalid_response"
    return "stable" if float(value) >= 35.0 else "phase_margin_insufficient"


def _load_resolved_run_config(path: Path) -> Any:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    circuit = raw["circuit_config"]
    for derived in (
        "topology_definition",
        "device_role_mapping",
        "cost_definition",
    ):
        circuit.pop(derived, None)
    return experiment_config_from_mapping(raw, base_directory=path.parent)


def _collect_suite(suite: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    state = json.loads((suite / "suite_state.json").read_text(encoding="utf-8"))
    if state.get("status") != "success":
        raise RuntimeError(f"suite is not complete: {suite}")
    summaries: list[dict[str, Any]] = []
    evaluations: list[dict[str, Any]] = []
    for cell in state["cells"].values():
        summary = load_summary(cell["run_directory"])
        resolved = _load_resolved_run_config(
            Path(summary["_run_directory"]) / "experiment_config.yaml"
        )
        summary["component_hashes"] = task7_component_hashes(resolved)
        summaries.append(summary)
        evaluations.extend(load_evaluations(cell["run_directory"]))
    order = {name: index for index, name in enumerate(METHODS)}
    summaries.sort(key=lambda row: (order[row["method"]], int(row["seed"])))
    evaluations.sort(
        key=lambda row: (order[row["method"]], int(row["seed"]), int(row["iteration"]))
    )
    return summaries, evaluations


def _write_combined_csv(
    summaries: list[dict[str, Any]], output: Path
) -> None:
    with output.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=TASK7_COLUMNS)
        writer.writeheader()
        for summary in summaries:
            source = Path(summary["_run_directory"]) / "evaluations.csv"
            with source.open("r", encoding="utf-8", newline="") as stream:
                for row in csv.DictReader(stream):
                    writer.writerow(row)


def _write_status_taxonomy(
    evaluations: list[dict[str, Any]], output: Path
) -> None:
    fields = (
        "experiment_id",
        "method",
        "seed",
        "iteration",
        "stability_status",
        "simulation_failed",
        "dc_non_convergence",
        "operating_region_invalid",
        "invalid_ac_response",
        "no_valid_unity_crossing",
        "ugf_right_censored",
        "phase_margin_insufficient",
        "transient_analysis_error",
        "slew_insufficient_transition",
    )
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in evaluations:
            op_error = str(row["analysis_errors"].get("op") or "").casefold()
            phase_margin = row["metrics"].get("phase_margin_deg")
            writer.writerow(
                {
                    "experiment_id": row["experiment_id"],
                    "method": row["method"],
                    "seed": row["seed"],
                    "iteration": row["iteration"],
                    "stability_status": _stability_status(row),
                    "simulation_failed": row["simulation_status"] != "success",
                    "dc_non_convergence": bool(op_error)
                    and (
                        "converg" in op_error
                        or "timestep too small" in op_error
                        or "singular matrix" in op_error
                    ),
                    "operating_region_invalid": (
                        str(row["operating_region_valid"]).casefold() != "true"
                    ),
                    "invalid_ac_response": (
                        bool(row["analysis_errors"].get("ac"))
                        or row["ugf_status"]
                        in {"invalid_response", "analysis_error"}
                    ),
                    "no_valid_unity_crossing": row["ugf_status"] == "no_crossing",
                    "ugf_right_censored": row["ugf_status"] == "right_censored",
                    "phase_margin_insufficient": (
                        row["phase_margin_status"] == "measured"
                        and phase_margin is not None
                        and float(phase_margin) < 35.0
                    ),
                    "transient_analysis_error": (
                        bool(row["analysis_errors"].get("transient"))
                        or row["positive_slew_status"]
                        in {"invalid_response", "analysis_error"}
                        or row["negative_slew_status"]
                        in {"invalid_response", "analysis_error"}
                    ),
                    "slew_insufficient_transition": (
                        row["positive_slew_status"] == "insufficient_transition"
                        or row["negative_slew_status"] == "insufficient_transition"
                    ),
                }
            )


def _detailed_statistics(
    summaries: list[dict[str, Any]], evaluations: list[dict[str, Any]]
) -> dict[str, Any]:
    metric_names = (
        "dc_gain_db",
        "ugf_hz",
        "phase_margin_deg",
        "dc_power_w",
        "output_dc_voltage",
        "positive_slew_v_per_s",
        "negative_slew_v_per_s",
    )
    result: dict[str, Any] = {}
    for method in METHODS:
        method_summaries = [row for row in summaries if row["method"] == method]
        rows = [row for row in evaluations if row["method"] == method]
        best = [row["best_result"] for row in method_summaries if row["best_result"]]
        stability: dict[str, int] = {}
        for row in rows:
            status = _stability_status(row)
            stability[status] = stability.get(status, 0) + 1
        constraints: dict[str, int] = {}
        for row in rows:
            for name, violation in row["constraint_components"].items():
                if float(violation) == 0.0:
                    constraints[name] = constraints.get(name, 0) + 1
        result[method] = {
            "run_count": len(method_summaries),
            "candidate_count": len(rows),
            "median_best_objective": median(
                float(row["objective_value"]) for row in best
            ),
            "median_best_constraint_violation": median(
                float(row["constraint_violation"]) for row in best
            ),
            "metric_distributions": {
                name: _distribution(
                    [
                        float(row["metrics"][name])
                        for row in rows
                        if row["metrics"].get(name) is not None
                    ]
                )
                for name in metric_names
            },
            "rates": {
                "op_invalid": mean(
                    float(row["operating_region_valid"] != "True")
                    for row in rows
                ),
                "ac_invalid": mean(
                    float(row["ugf_status"] in {"invalid_response", "analysis_error"})
                    for row in rows
                ),
                "no_valid_ugf": mean(
                    float(row["ugf_status"] != "measured") for row in rows
                ),
                "ugf_right_censored": mean(
                    float(row["ugf_status"] == "right_censored") for row in rows
                ),
                "phase_margin_insufficient": mean(
                    float(_stability_status(row) == "phase_margin_insufficient")
                    for row in rows
                ),
                "transient_failure": mean(
                    float(
                        bool(row["analysis_errors"].get("transient"))
                        or row["positive_slew_status"] in {"invalid_response", "analysis_error"}
                        or row["negative_slew_status"] in {"invalid_response", "analysis_error"}
                    )
                    for row in rows
                ),
                "slew_insufficient_transition": mean(
                    float(
                        row["positive_slew_status"] == "insufficient_transition"
                        or row["negative_slew_status"] == "insufficient_transition"
                    )
                    for row in rows
                ),
                "simulation_failed": mean(
                    float(row["simulation_status"] != "success") for row in rows
                ),
            },
            "stability_status_counts": stability,
            "constraint_pass_counts": constraints,
            "exact_cost_totals": {
                name: sum(int(row[name]) for row in method_summaries)
                for name in (
                    "candidate_evaluations",
                    "ngspice_process_calls",
                    "op_calls",
                    "ac_calls",
                    "transient_calls",
                    "high_fidelity_analysis_calls",
                    "screening_calls",
                )
            },
        }
    return result


def _cost_profile(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    result = {
        name: _distribution([float(row[name]) for row in evaluations])
        for name in (
            "op_runtime_seconds",
            "ac_runtime_seconds",
            "transient_runtime_seconds",
            "wall_clock_seconds",
        )
    }
    overhead = [
        max(
            0.0,
            float(row["wall_clock_seconds"])
            - float(row["op_runtime_seconds"])
            - float(row["ac_runtime_seconds"])
            - float(row["transient_runtime_seconds"]),
        )
        for row in evaluations
    ]
    result["orchestration_file_parse_overhead_seconds"] = _distribution(overhead)
    result["interpretation"] = {
        "analysis_runtime": (
            "Each OP/AC/transient runtime includes its independent process startup, "
            "SKY130 model loading, analysis computation, copying, and parsing."
        ),
        "separation_limit": (
            "ngspice does not expose a trustworthy portable split between model/process "
            "startup and solver computation; no synthetic split is reported."
        ),
    }
    return result


def _copy_best_raw_evidence(
    summaries: list[dict[str, Any]], output: Path
) -> list[dict[str, Any]]:
    mappings = []
    for summary in summaries:
        best = summary.get("best_result")
        if not best or not best.get("is_feasible"):
            continue
        iteration = int(best["iteration"])
        label = f"{summary['method']}_seed{int(summary['seed'])}"
        source = (
            Path(summary["_run_directory"])
            / "runs"
            / f"evaluation_{iteration:04d}"
        )
        destination = output / label
        shutil.copytree(source, destination, dirs_exist_ok=True)
        mappings.append(
            {
                "method": summary["method"],
                "seed": int(summary["seed"]),
                "iteration": iteration,
                "destination": label,
                "metrics": best["metrics"],
                "parameters": best["parameters"],
            }
        )
    _write_json(output / "index.json", mappings)
    return mappings


def publish_suite(suite: Path, destination: Path, design: str) -> None:
    summaries, evaluations = _collect_suite(suite)
    seeds = tuple(range(3)) if design == "smoke" else tuple(range(10))
    budget = 25 if design == "smoke" else 50
    fairness = validate_fairness(
        summaries,
        methods=METHODS,
        seeds=seeds,
        design=design,
        candidate_budget=budget,
    )
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("suite_state.json", "fairness_validation.json"):
        shutil.copy2(suite / name, destination / name)
    _write_json(destination / "expanded_fairness_validation.json", {
        **fairness,
        "component_hashes": dict(TASK7_COMPONENT_HASHES),
        "component_binding": (
            "All components are bound by the identical benchmark and protocol "
            "family hashes present in every candidate and run manifest."
        ),
    })
    _write_json(
        destination / "cell_summaries.json",
        [
            {key: value for key, value in row.items() if key != "_run_directory"}
            for row in summaries
        ],
    )
    _write_combined_csv(summaries, destination / "evaluations.csv")
    _write_status_taxonomy(evaluations, destination / "status_taxonomy.csv")
    write_statistics(summaries, destination / "statistics", budget)
    _write_json(
        destination / "detailed_statistics.json",
        _detailed_statistics(summaries, evaluations),
    )
    _write_json(
        destination / "statistics" / "analysis_cost_profile.json",
        _cost_profile(evaluations),
    )
    if design == "formal":
        _copy_best_raw_evidence(summaries, destination / "best_raw_evidence")


def write_calibration_details(output: Path) -> None:
    path = output / "calibration" / "calibration.csv"
    with path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        row["metrics"] = json.loads(row["metrics"])
        row["errors"] = json.loads(row["errors"])
    metric_names = (
        "dc_gain_db",
        "ugf_hz",
        "phase_margin_deg",
        "dc_power_w",
        "output_dc_voltage",
        "positive_slew_v_per_s",
        "negative_slew_v_per_s",
    )
    _write_json(
        output / "calibration" / "detailed_statistics.json",
        {
            "candidate_count": len(rows),
            "metric_distributions": {
                name: _distribution(
                    [
                        float(row["metrics"][name])
                        for row in rows
                        if row["metrics"].get(name) is not None
                    ]
                )
                for name in metric_names
            },
            "status_counts": {
                field: {
                    value: sum(row[field] == value for row in rows)
                    for value in sorted({row[field] for row in rows})
                }
                for field in (
                    "ugf_status",
                    "phase_margin_status",
                    "positive_slew_status",
                    "negative_slew_status",
                    "operating_region_valid",
                )
            },
            "derived_counts": {
                "no_valid_ugf": sum(row["ugf_status"] != "measured" for row in rows),
                "ugf_right_censored": sum(
                    row["ugf_status"] == "right_censored" for row in rows
                ),
                "phase_margin_insufficient": sum(
                    row["phase_margin_status"] == "measured"
                    and row["metrics"].get("phase_margin_deg") is not None
                    and float(row["metrics"]["phase_margin_deg"]) < 35.0
                    for row in rows
                ),
                "transient_invalid": sum(
                    row["positive_slew_status"] in {"invalid_response", "analysis_error"}
                    or row["negative_slew_status"] in {"invalid_response", "analysis_error"}
                    for row in rows
                ),
                "op_invalid": sum(
                    row["operating_region_valid"] == "false" for row in rows
                ),
                "simulation_errors": sum(
                    any(row["errors"].values()) for row in rows
                ),
            },
        },
    )


def write_hash_manifest(output: Path) -> None:
    hashes = {
        path.relative_to(output).as_posix(): _file_hash(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "file_hashes.json"
    }
    _write_json(
        output / "file_hashes.json",
        {
            "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
            "task7_search_space_hash": TASK7_SEARCH_SPACE_HASH,
            "task7_protocol_family_hash": protocol_family_hash(),
            "files": hashes,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-suite", type=Path, required=True)
    parser.add_argument("--formal-suite", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/sky130/two_stage_ota/results"),
    )
    args = parser.parse_args()
    output = args.output.resolve()
    write_calibration_details(output)
    publish_suite(args.smoke_suite.resolve(), output / "smoke", "smoke")
    publish_suite(args.formal_suite.resolve(), output / "formal", "formal")
    write_hash_manifest(output)
    print(output)


if __name__ == "__main__":
    main()
