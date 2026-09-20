"""Full-only PVT matrix collector used before the formal Task 9 evaluator.

The script has no optimizer loop and no hierarchical short circuit.  Every
candidate always attempts OP, AC, and transient at every frozen PVT corner.
It is used only for the nominal-to-PVT gap and independent Sobol calibration.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
from dataclasses import fields
from hashlib import sha256
import json
from math import isfinite
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from time import monotonic
from types import SimpleNamespace
from typing import Any, Iterable, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from circuitpilot.experiments.config import load_experiment_config  # noqa: E402
from circuitpilot.parser import parse_ac_output  # noqa: E402
from circuitpilot.simulator import run_ngspice  # noqa: E402
from circuitpilot.sky130_two_stage_ota import (  # noqa: E402
    PhaseMarginStatus,
    SlewStatus,
    UgfStatus,
    assess_task7_operating_regions,
    generate_task7_ac_netlist,
    generate_task7_op_netlist,
    generate_task7_transient_netlist,
    measure_task7_slew,
    measure_task7_stability,
    optional_minus_3db_bandwidth,
    parse_task7_operating_point,
    parse_task7_transient,
)
from circuitpilot.task7_protocol import Task7Specification, stable_hash  # noqa: E402
from circuitpilot.task8_protocol import TASK8_SPECIFICATION  # noqa: E402


TASK7_FROZEN = PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task7_frozen.yaml"
PROCESS_CORNERS = ("tt", "ss", "ff", "fs", "sf")
VT_CONDITIONS = (
    ("nominal", 1.80, 27.0),
    ("low_v_high_t", 1.62, 125.0),
    ("high_v_low_t", 1.98, -40.0),
)
CORNERS = tuple(
    {
        "corner_id": f"{process}__{condition}",
        "process_corner": process,
        "condition": condition,
        "vdd_v": vdd,
        "temperature_c": temperature,
    }
    for process in PROCESS_CORNERS
    for condition, vdd, temperature in VT_CONDITIONS
)
CANONICAL_METRICS = (
    "dc_gain_db",
    "ugf_hz",
    "ugf_lower_bound_hz",
    "phase_margin_deg",
    "minus_3db_bandwidth_hz",
    "dc_power_w",
    "supply_current_a",
    "output_dc_voltage",
    "stage1_dc_voltage",
    "positive_slew_v_per_s",
    "negative_slew_v_per_s",
    "operating_region_valid",
)
TEMPERATURE_PATTERN = re.compile(r"Doing analysis at TEMP\s*=\s*([-+0-9.eE]+)")
NOMINAL_SOURCES = (
    "research/sky130/two_stage_ota/results/calibration/calibration.csv",
    "research/sky130/two_stage_ota/results/smoke/evaluations.csv",
    "research/sky130/two_stage_ota/results/formal/evaluations.csv",
    "research/sky130/two_stage_ota/task8/results/smoke/evaluations.csv",
    "research/sky130/two_stage_ota/task8/results/equal_candidate/evaluations.csv",
    "research/sky130/two_stage_ota/task8/results/equal_simulation_time/evaluations.csv",
)


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def collect_nominal_feasible_designs() -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for relative in NOMINAL_SOURCES:
        path = PROJECT_ROOT / relative
        with path.open("r", encoding="utf-8", newline="") as stream:
            for row in csv.DictReader(stream):
                if str(row.get("is_feasible", "")).lower() != "true":
                    continue
                parameters = json.loads(row["parameters"])
                key = canonical_json(parameters)
                if key not in unique:
                    unique[key] = {
                        "design_id": "nominal_" + sha256(key.encode("utf-8")).hexdigest()[:16],
                        "parameters": parameters,
                        "sources": [],
                    }
                unique[key]["sources"].append(
                    {
                        "file": relative,
                        "experiment_id": row.get("experiment_id"),
                        "run_id": row.get("run_id"),
                        "method": row.get("method"),
                        "seed": int(row["seed"]) if row.get("seed") else None,
                        "iteration": int(row["iteration"]) if row.get("iteration") else None,
                    }
                )
    designs = sorted(unique.values(), key=lambda item: item["design_id"])
    return designs


def load_candidate_file(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = payload["designs"] if isinstance(payload, dict) else payload
    if not isinstance(candidates, list):
        raise ValueError("candidate JSON must be a list or contain designs")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(candidates):
        if not isinstance(item, dict) or not isinstance(item.get("parameters"), dict):
            raise ValueError(f"candidate {index} has no parameter mapping")
        parameters = {name: float(value) for name, value in item["parameters"].items()}
        result.append(
            {
                "design_id": str(item.get("design_id") or f"candidate_{index:04d}"),
                "parameters": parameters,
                "sources": list(item.get("sources", [])),
            }
        )
    return result


def prepare_model_cache(base_config: Any) -> dict[str, dict[str, str]]:
    model = base_config.model
    identity = model.expected_model_sha256 or model.model_sha256()
    root = Path(tempfile.gettempdir()) / "circuitpilot-task9-pvt-cache" / identity[:20]
    root.mkdir(parents=True, exist_ok=True)
    primitive_root = model.pdk_root / "libs.ref" / "sky130_fd_pr" / "spice"
    result: dict[str, dict[str, str]] = {}
    for process in PROCESS_CORNERS:
        directory = root / process
        directory.mkdir(parents=True, exist_ok=True)
        invariant = directory / "invariant.spice"
        shutil.copy2(model.invariant_path, invariant)
        names: dict[str, str] = {"invariant": invariant.as_posix()}
        for polarity in ("nfet", "pfet"):
            for suffix in ("corner", "pm3"):
                filename = f"sky130_fd_pr__{polarity}_01v8__{process}.{suffix}.spice"
                source = primitive_root / filename
                if not source.is_file():
                    raise FileNotFoundError(source)
                destination = directory / filename
                shutil.copy2(source, destination)
                names[f"{polarity}_{suffix}"] = destination.as_posix()
        result[process] = names
    return result


def pvt_config(base_config: Any, corner: Mapping[str, Any]) -> Any:
    values = {field.name: getattr(base_config, field.name) for field in fields(base_config)}
    values["supply_voltage_v"] = float(corner["vdd_v"])
    values["temperature_c"] = float(corner["temperature_c"])
    return SimpleNamespace(**values)


def execute_stage(
    kind: str,
    *,
    config: Any,
    parameters: Mapping[str, float],
    model_paths: Mapping[str, str],
    executable: str,
    timeout_seconds: float,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
) -> dict[str, Any]:
    started = monotonic()
    metrics: dict[str, float | None] = {}
    statuses: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    error: str | None = None
    process_seconds = 0.0
    reported_temperature: float | None = None
    with tempfile.TemporaryDirectory(prefix=f"cp-t9-{kind}-") as temporary:
        directory = Path(temporary)
        netlist_path = directory / "circuit.cir"
        data_path = directory / "data.dat"
        op_path = directory / "op.dat"
        device_path = directory / "device_op.dat"
        log_path = directory / "ngspice.log"
        common = {
            "invariant_path": model_paths["invariant"],
            "nfet_corner_path": model_paths["nfet_corner"],
            "pfet_corner_path": model_paths["pfet_corner"],
        }
        try:
            if kind == "op":
                text = generate_task7_op_netlist(
                    config,
                    parameters,
                    **common,
                    op_output_path=op_path.as_posix(),
                    device_op_output_path=device_path.as_posix(),
                )
            elif kind == "ac":
                text = generate_task7_ac_netlist(
                    config,
                    parameters,
                    **common,
                    ac_output_path=data_path.as_posix(),
                    start_frequency_hz=start_frequency_hz,
                    stop_frequency_hz=stop_frequency_hz,
                    points_per_decade=points_per_decade,
                )
            elif kind == "transient":
                text = generate_task7_transient_netlist(
                    config,
                    parameters,
                    **common,
                    transient_output_path=data_path.as_posix(),
                )
            else:
                raise ValueError(f"unknown analysis kind {kind}")
            netlist_path.write_text(text, encoding="utf-8")
            process = run_ngspice(
                netlist_path,
                executable=executable,
                timeout_seconds=timeout_seconds,
                log_path=log_path,
            )
            process_seconds = process.elapsed_seconds
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            match = TEMPERATURE_PATTERN.search(log_text)
            if match is not None:
                reported_temperature = float(match.group(1))
            if kind == "op":
                op = parse_task7_operating_point(op_path, device_path)
                region = assess_task7_operating_regions(op)
                metrics = {
                    "dc_power_w": op.dc_power_w,
                    "supply_current_a": op.supply_current_a,
                    "output_dc_voltage": op.output_voltage_v,
                    "stage1_dc_voltage": op.stage1_voltage_v,
                    "operating_region_valid": float(region.valid),
                }
                evidence = {
                    "measured_supply_voltage_v": op.supply_voltage_v,
                    "operating_region_mask": region.violation_mask,
                    "operating_region_types": list(region.violation_types),
                    "device_status": dict(region.device_status),
                    "device_quantities": {
                        role: dict(values) for role, values in op.device_quantities.items()
                    },
                }
            elif kind == "ac":
                response = parse_ac_output(data_path)
                stability = measure_task7_stability(response)
                metrics = {
                    "dc_gain_db": stability.dc_gain_db,
                    "ugf_hz": stability.ugf_hz,
                    "ugf_lower_bound_hz": stability.ugf_lower_bound_hz,
                    "phase_margin_deg": stability.phase_margin_deg,
                    "minus_3db_bandwidth_hz": optional_minus_3db_bandwidth(response),
                }
                statuses = {
                    "ugf_status": stability.ugf_status.value,
                    "phase_margin_status": stability.phase_margin_status.value,
                    "ugf_crossing_count": stability.crossing_count,
                }
            else:
                response = parse_task7_transient(data_path)
                slew = measure_task7_slew(response, config)
                metrics = {
                    "positive_slew_v_per_s": slew.positive_slew_v_per_s,
                    "negative_slew_v_per_s": slew.negative_slew_v_per_s,
                }
                statuses = {
                    "positive_slew_status": slew.positive_status.value,
                    "negative_slew_status": slew.negative_status.value,
                }
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            if kind == "ac":
                statuses = {
                    "ugf_status": UgfStatus.ANALYSIS_ERROR.value,
                    "phase_margin_status": PhaseMarginStatus.ANALYSIS_ERROR.value,
                    "ugf_crossing_count": 0,
                }
            elif kind == "transient":
                statuses = {
                    "positive_slew_status": SlewStatus.ANALYSIS_ERROR.value,
                    "negative_slew_status": SlewStatus.ANALYSIS_ERROR.value,
                }
    return {
        "kind": kind,
        "metrics": metrics,
        "statuses": statuses,
        "evidence": evidence,
        "error": error,
        "process_elapsed_seconds": process_seconds,
        "outer_elapsed_seconds": monotonic() - started,
        "reported_temperature_c": reported_temperature,
    }


def constraint_evaluation(
    metrics: Mapping[str, float | None],
    statuses: Mapping[str, Any],
    specification: Task7Specification,
) -> dict[str, Any]:
    def finite_value(name: str) -> float | None:
        value = metrics.get(name)
        if value is None:
            return None
        numeric = float(value)
        return numeric if isfinite(numeric) else None

    def lower(name: str, threshold: float, status_ok: bool = True) -> float:
        value = finite_value(name)
        if value is None or not status_ok:
            return 1.0
        return max(0.0, threshold - value) / max(abs(threshold), 1e-30)

    def upper(name: str, threshold: float) -> float:
        value = finite_value(name)
        if value is None:
            return 1.0
        return max(0.0, value - threshold) / max(abs(threshold), 1e-30)

    ugf_status = str(statuses.get("ugf_status", "analysis_error"))
    ugf_value_name = "ugf_hz"
    ugf_ok = ugf_status == UgfStatus.MEASURED.value
    if ugf_status == UgfStatus.RIGHT_CENSORED.value:
        ugf_value_name = "ugf_lower_bound_hz"
        ugf_ok = finite_value(ugf_value_name) is not None
    components = {
        "gain_min": lower("dc_gain_db", specification.gain_min_db),
        "ugf_min": lower(ugf_value_name, specification.ugf_min_hz, ugf_ok),
        "phase_margin_min": lower(
            "phase_margin_deg",
            specification.phase_margin_min_deg,
            statuses.get("phase_margin_status") == PhaseMarginStatus.MEASURED.value,
        ),
        "power_max": upper("dc_power_w", specification.power_max_w),
        "positive_slew_min": lower(
            "positive_slew_v_per_s",
            specification.positive_slew_min_v_per_s,
            statuses.get("positive_slew_status") == SlewStatus.MEASURED.value,
        ),
        "negative_slew_min": lower(
            "negative_slew_v_per_s",
            specification.negative_slew_min_v_per_s,
            statuses.get("negative_slew_status") == SlewStatus.MEASURED.value,
        ),
        "output_low": lower("output_dc_voltage", specification.output_min_v),
        "output_high": upper("output_dc_voltage", specification.output_max_v),
        "operating_region": lower("operating_region_valid", 1.0),
    }
    total = sum(components.values())
    return {
        "constraint_components": components,
        "constraint_violation": total,
        "is_feasible": total == 0.0,
    }


def evaluate_corner(
    *,
    base_config: Any,
    parameters: Mapping[str, float],
    corner: Mapping[str, Any],
    model_paths: Mapping[str, str],
    executable: str,
    timeout_seconds: float,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
) -> dict[str, Any]:
    config = pvt_config(base_config, corner)
    stages = [
        execute_stage(
            kind,
            config=config,
            parameters=parameters,
            model_paths=model_paths,
            executable=executable,
            timeout_seconds=timeout_seconds,
            start_frequency_hz=start_frequency_hz,
            stop_frequency_hz=stop_frequency_hz,
            points_per_decade=points_per_decade,
        )
        for kind in ("op", "ac", "transient")
    ]
    metrics: dict[str, float | None] = {name: None for name in CANONICAL_METRICS}
    statuses: dict[str, Any] = {
        "ugf_status": "analysis_error",
        "phase_margin_status": "analysis_error",
        "ugf_crossing_count": 0,
        "positive_slew_status": "analysis_error",
        "negative_slew_status": "analysis_error",
    }
    evidence: dict[str, Any] = {}
    errors: dict[str, str | None] = {}
    for stage in stages:
        metrics.update(stage["metrics"])
        statuses.update(stage["statuses"])
        evidence.update(stage["evidence"])
        errors[stage["kind"]] = stage["error"]
    applied_vdd = evidence.get("measured_supply_voltage_v")
    vdd_ok = applied_vdd is not None and abs(float(applied_vdd) - float(corner["vdd_v"])) <= 1e-9
    temperature_ok = all(
        stage["reported_temperature_c"] is not None
        and abs(float(stage["reported_temperature_c"]) - float(corner["temperature_c"])) <= 1e-9
        for stage in stages
    )
    objective = constraint_evaluation(metrics, statuses, TASK8_SPECIFICATION)
    return {
        **dict(corner),
        "metrics": metrics,
        "statuses": statuses,
        "evidence": evidence,
        "analysis_errors": errors,
        **objective,
        "application_checks": {
            "vdd_applied": vdd_ok,
            "temperature_applied_all_stages": temperature_ok,
        },
        "cost": {
            "op_calls": 1,
            "ac_calls": 1,
            "transient_calls": 1,
            "process_calls": 3,
            "accumulated_ngspice_seconds": sum(
                float(stage["process_elapsed_seconds"]) for stage in stages
            ),
            "outer_wall_seconds": sum(float(stage["outer_elapsed_seconds"]) for stage in stages),
            "per_stage_ngspice_seconds": {
                stage["kind"]: float(stage["process_elapsed_seconds"]) for stage in stages
            },
        },
    }


def summarize_design(design: Mapping[str, Any], corners: list[dict[str, Any]]) -> dict[str, Any]:
    component_names = tuple(corners[0]["constraint_components"])
    robust_components = {
        name: max(float(corner["constraint_components"][name]) for corner in corners)
        for name in component_names
    }
    return {
        "schema_version": "task9_full_pvt_research_matrix_v1",
        "design_id": design["design_id"],
        "parameters": design["parameters"],
        "sources": design.get("sources", []),
        "corners": corners,
        "pvt_feasible": all(bool(corner["is_feasible"]) for corner in corners),
        "robust_constraint_components": robust_components,
        "robust_constraint_violation": sum(robust_components.values()),
        "cost": {
            "corners_started": len(corners),
            "corners_completed": len(corners),
            "op_calls": len(corners),
            "ac_calls": len(corners),
            "transient_calls": len(corners),
            "process_calls": 3 * len(corners),
            "accumulated_ngspice_seconds": sum(
                float(corner["cost"]["accumulated_ngspice_seconds"]) for corner in corners
            ),
            "outer_wall_seconds": sum(float(corner["cost"]["outer_wall_seconds"]) for corner in corners),
        },
    }


def evaluate_design(
    design: dict[str, Any],
    *,
    output_root: Path,
    base_config: Any,
    caches: Mapping[str, Mapping[str, str]],
    executable: str,
    timeout_seconds: float,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
) -> dict[str, Any]:
    checkpoint = output_root / "designs" / f"{design['design_id']}.json"
    if checkpoint.is_file():
        existing = json.loads(checkpoint.read_text(encoding="utf-8"))
        if existing.get("parameters") != design["parameters"]:
            raise RuntimeError(f"checkpoint identity changed for {design['design_id']}")
        corners = list(existing.get("corners", []))
    else:
        corners = []
    completed = {corner["corner_id"] for corner in corners}
    for corner in CORNERS:
        if corner["corner_id"] in completed:
            continue
        corners.append(
            evaluate_corner(
                base_config=base_config,
                parameters=design["parameters"],
                corner=corner,
                model_paths=caches[corner["process_corner"]],
                executable=executable,
                timeout_seconds=timeout_seconds,
                start_frequency_hz=start_frequency_hz,
                stop_frequency_hz=stop_frequency_hz,
                points_per_decade=points_per_decade,
            )
        )
        _atomic_json(checkpoint, summarize_design(design, corners))
    result = summarize_design(design, corners)
    _atomic_json(checkpoint, result)
    return result


def write_outputs(
    output_root: Path,
    designs: list[dict[str, Any]],
    results: Iterable[dict[str, Any]],
    *,
    source_kind: str,
    candidate_file: Path | None,
) -> dict[str, Any]:
    ordered = sorted(results, key=lambda item: item["design_id"])
    matrix_path = output_root / "full_pvt_matrix.jsonl"
    matrix_path.write_text(
        "".join(json.dumps(item, sort_keys=True, allow_nan=False) + "\n" for item in ordered),
        encoding="utf-8",
    )
    rows: list[dict[str, Any]] = []
    for design in ordered:
        for corner in design["corners"]:
            rows.append(
                {
                    "design_id": design["design_id"],
                    "corner_id": corner["corner_id"],
                    "process_corner": corner["process_corner"],
                    "condition": corner["condition"],
                    "vdd_v": corner["vdd_v"],
                    "temperature_c": corner["temperature_c"],
                    "corner_feasible": corner["is_feasible"],
                    "constraint_violation": corner["constraint_violation"],
                    **corner["metrics"],
                    **corner["statuses"],
                    "analysis_errors": canonical_json(corner["analysis_errors"]),
                    "constraint_components": canonical_json(corner["constraint_components"]),
                    **corner["cost"],
                }
            )
    csv_path = output_root / "corner_matrix.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "schema_version": "task9_full_pvt_research_summary_v1",
        "source_kind": source_kind,
        "candidate_file": None if candidate_file is None else str(candidate_file),
        "candidate_count": len(ordered),
        "corner_count": len(CORNERS),
        "corner_matrix_rows": len(rows),
        "pvt_feasible_count_row0": sum(bool(item["pvt_feasible"]) for item in ordered),
        "pvt_infeasible_count_row0": sum(not bool(item["pvt_feasible"]) for item in ordered),
        "total_process_calls": sum(item["cost"]["process_calls"] for item in ordered),
        "total_accumulated_ngspice_seconds": sum(
            item["cost"]["accumulated_ngspice_seconds"] for item in ordered
        ),
        "all_vdd_checks_passed": all(
            corner["application_checks"]["vdd_applied"]
            for item in ordered
            for corner in item["corners"]
        ),
        "all_temperature_checks_passed": all(
            corner["application_checks"]["temperature_applied_all_stages"]
            for item in ordered
            for corner in item["corners"]
        ),
        "task7_frozen_sha256": file_sha256(TASK7_FROZEN),
        "candidate_set_hash": stable_hash(
            [{"design_id": item["design_id"], "parameters": item["parameters"]} for item in designs]
        ),
        "corner_suite_hash": stable_hash(CORNERS),
        "matrix_sha256": file_sha256(matrix_path),
        "corner_csv_sha256": file_sha256(csv_path),
        "source_file_sha256": {
            relative: file_sha256(PROJECT_ROOT / relative) for relative in NOMINAL_SOURCES
        }
        if source_kind == "nominal-gap"
        else {},
    }
    _atomic_json(output_root / "summary.json", summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("nominal-gap", "json"), required=True)
    parser.add_argument("--candidates", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--ngspice", default="ngspice")
    parser.add_argument("--timeout", type=float, default=60.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    if args.source == "nominal-gap":
        designs = collect_nominal_feasible_designs()
        candidate_file = None
    else:
        if args.candidates is None:
            raise ValueError("--candidates is required with --source json")
        candidate_file = args.candidates.resolve()
        designs = load_candidate_file(candidate_file)
    _atomic_json(
        output_root / "candidate_set.json",
        {"schema_version": "task9_candidate_set_v1", "designs": designs},
    )
    experiment = load_experiment_config(TASK7_FROZEN)
    base_config = experiment.circuit_config
    if base_config is None:
        raise RuntimeError("Task 7 frozen config has no OTA circuit configuration")
    caches = prepare_model_cache(base_config)
    worker_count = max(1, min(int(args.workers), len(designs)))
    kwargs = {
        "output_root": output_root,
        "base_config": base_config,
        "caches": caches,
        "executable": args.ngspice,
        "timeout_seconds": args.timeout,
        "start_frequency_hz": experiment.ngspice_config.start_frequency_hz,
        "stop_frequency_hz": experiment.ngspice_config.stop_frequency_hz,
        "points_per_decade": experiment.ngspice_config.points_per_decade,
    }
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        pending = {executor.submit(evaluate_design, design, **kwargs): design for design in designs}
        for future in as_completed(pending):
            result = future.result()
            results.append(result)
            print(
                f"completed {len(results)}/{len(designs)} {result['design_id']} "
                f"pvt_feasible={result['pvt_feasible']}",
                flush=True,
            )
    summary = write_outputs(
        output_root,
        designs,
        results,
        source_kind=args.source,
        candidate_file=candidate_file,
    )
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
