"""Run-level and method-level statistics derived from evaluation CSV evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import fmean, median, pstdev
from typing import Any, Iterable

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.survival import kaplan_meier


RESULT_COLUMNS = (
    "method", "seed", "run_id", "output_directory", "simulation_budget",
    "evaluations_total", "evaluations_success", "evaluations_failed", "ngspice_calls",
    "best_objective", "best_parameters", "best_metrics", "is_feasible",
    "first_feasible_iteration", "simulations_to_first_feasible",
    "event_observed", "evaluation_time", "budget_at_censoring",
    "total_runtime", "mean_simulation_time", "best_constraint_violation",
    "best_gain", "best_bandwidth", "best_bandwidth_lower_bound", "best_power",
    "ngspice_failure_rate", "analysis_error_rate", "invalid_response_rate",
    "bandwidth_right_censored_rate", "complete_exact_metric_rate",
)

SUMMARY_COLUMNS = (
    "method", "runs", "success_rate", "median_best_objective",
    "mean_best_objective", "std_best_objective",
    "median_simulations_to_first_feasible", "censored_runs",
    "median_constraint_violation", "mean_runtime", "mean_simulation_time",
    "failure_rate", "ngspice_failure_rate", "analysis_error_rate",
    "invalid_response_rate", "bandwidth_right_censored_rate",
    "complete_exact_metric_rate", "ngspice_calls", "event_observed_count",
    "censored_count", "km_median_time_to_feasible", "rmst",
    "best_gain", "best_bandwidth", "best_bandwidth_lower_bound", "best_power",
)


def load_evaluations(run_directory: str | Path) -> list[dict[str, Any]]:
    """Load one canonical evaluations.csv without replacing missing values."""
    source = Path(run_directory).resolve() / "evaluations.csv"
    try:
        with source.open("r", encoding="utf-8", newline="") as stream:
            raw_rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise ResearchExperimentError(f"cannot read evaluations CSV '{source}': {exc}") from exc
    rows: list[dict[str, Any]] = []
    for raw in raw_rows:
        try:
            rows.append({
                **raw,
                "seed": int(raw["seed"]),
                "iteration": int(raw["iteration"]),
                "parameters": json.loads(raw["parameters"]),
                "raw_metrics": json.loads(raw["raw_metrics"]),
                "objective_value": None if raw["objective_value"] == "" else float(raw["objective_value"]),
                "constraint_violation": None if raw["constraint_violation"] == "" else float(raw["constraint_violation"]),
                "simulation_time": float(raw["simulation_time"]),
                "total_elapsed_time": float(raw["total_elapsed_time"]),
                "ngspice_called": raw["ngspice_called"].lower() == "true",
                "is_feasible": raw["is_feasible"].lower() == "true",
                "measurement_status": raw.get("measurement_status") or None,
                "bandwidth_status": raw.get("bandwidth_status") or None,
                "bandwidth_lower_bound_hz": (
                    None
                    if raw.get("bandwidth_lower_bound_hz", "") == ""
                    else float(raw["bandwidth_lower_bound_hz"])
                ),
                "experiment_phase": raw.get("experiment_phase", "baseline"),
                "event_observed": raw.get("event_observed", "false").lower() == "true",
                "evaluation_time": (
                    None
                    if raw.get("evaluation_time", "") == ""
                    else int(raw["evaluation_time"])
                ),
            })
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ResearchExperimentError(f"invalid evaluation row in '{source}': {exc}") from exc
    return rows


def summarize_run(run_directory: str | Path) -> dict[str, Any]:
    """Build one result row exclusively from manifest/config and evaluation CSV."""
    directory = Path(run_directory).resolve()
    rows = load_evaluations(directory)
    if not rows:
        raise ResearchExperimentError(f"run '{directory}' has no evaluations")
    phases = {row["experiment_phase"] for row in rows}
    if phases == {"calibration"}:
        raise ResearchExperimentError("calibration evaluations cannot enter baseline summaries")
    if len(phases) != 1:
        raise ResearchExperimentError("a run cannot mix experiment phases")
    try:
        manifest = json.loads((directory / "research_manifest.json").read_text(encoding="utf-8"))
        budget = int(manifest["configuration"]["experiment"]["simulation_budget"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ResearchExperimentError(f"cannot read run manifest '{directory}': {exc}") from exc
    process_successful = [
        row for row in rows if row["simulation_status"] == "success"
    ]
    successful = [
        row
        for row in rows
        if row["simulation_status"] == "success"
        and row["objective_value"] is not None
        and row["constraint_violation"] is not None
    ]
    best = min(successful, key=lambda row: (float(row["constraint_violation"]), float(row["objective_value"]), row["iteration"])) if successful else None
    first_feasible = next((row for row in rows if row["is_feasible"]), None)
    best_metrics = {} if best is None else best["raw_metrics"]
    observed_violations = [
        float(row["constraint_violation"])
        for row in rows
        if row["constraint_violation"] is not None
    ]
    exact_bandwidths = [
        float(row["raw_metrics"]["bandwidth_hz"])
        for row in rows
        if row["raw_metrics"].get("bandwidth_hz") is not None
    ]
    bandwidth_bounds = [
        float(row["bandwidth_lower_bound_hz"])
        for row in rows
        if row["bandwidth_lower_bound_hz"] is not None
    ]
    count = len(rows)
    return {
        "method": rows[0]["method"], "seed": rows[0]["seed"], "run_id": rows[0]["run_id"],
        "output_directory": str(directory), "simulation_budget": budget,
        "evaluations_total": len(rows), "evaluations_success": len(process_successful),
        "evaluations_failed": len(rows) - len(process_successful),
        "ngspice_calls": sum(bool(row["ngspice_called"]) for row in rows),
        "best_objective": None if best is None else best["objective_value"],
        "best_parameters": None if best is None else best["parameters"],
        "best_metrics": None if best is None else best["raw_metrics"],
        "is_feasible": first_feasible is not None,
        "first_feasible_iteration": None if first_feasible is None else first_feasible["iteration"],
        "simulations_to_first_feasible": None if first_feasible is None else first_feasible["iteration"],
        "event_observed": first_feasible is not None,
        "evaluation_time": (
            first_feasible["iteration"] if first_feasible is not None else len(rows)
        ),
        "budget_at_censoring": None if first_feasible is not None else budget,
        "total_runtime": max(row["total_elapsed_time"] for row in rows),
        "mean_simulation_time": fmean(row["simulation_time"] for row in rows),
        "best_constraint_violation": min(observed_violations) if observed_violations else None,
        "best_gain": best_metrics.get("gain_db"),
        "best_bandwidth": max(exact_bandwidths) if exact_bandwidths else None,
        "best_bandwidth_lower_bound": max(bandwidth_bounds) if bandwidth_bounds else None,
        "best_power": best_metrics.get("dc_power_w"),
        "ngspice_failure_rate": sum(
            row["simulation_status"] == "simulation_failed" for row in rows
        ) / count,
        "analysis_error_rate": sum(
            row["measurement_status"] == "analysis_error" for row in rows
        ) / count,
        "invalid_response_rate": sum(
            row["measurement_status"] == "invalid_response" for row in rows
        ) / count,
        "bandwidth_right_censored_rate": sum(
            row["bandwidth_status"] == "right_censored" for row in rows
        ) / count,
        "complete_exact_metric_rate": sum(
            row["bandwidth_status"] == "measured" for row in rows
        ) / count,
    }


def summarize_methods(results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate methods without imputing values for unsuccessful/censored runs."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        groups.setdefault(str(result["method"]), []).append(result)
    summaries = []
    for method, rows in sorted(groups.items()):
        objectives = [float(row["best_objective"]) for row in rows if row["best_objective"] is not None]
        firsts = [int(row["simulations_to_first_feasible"]) for row in rows if row["simulations_to_first_feasible"] is not None]
        violations = [float(row["best_constraint_violation"]) for row in rows if row["best_constraint_violation"] is not None]
        simulation_times = [float(row["mean_simulation_time"]) for row in rows]
        best_gains = [float(row["best_gain"]) for row in rows if row["best_gain"] is not None]
        best_bandwidths = [float(row["best_bandwidth"]) for row in rows if row["best_bandwidth"] is not None]
        best_bandwidth_bounds = [float(row["best_bandwidth_lower_bound"]) for row in rows if row.get("best_bandwidth_lower_bound") is not None]
        best_powers = [float(row["best_power"]) for row in rows if row["best_power"] is not None]
        total_evaluations = sum(int(row["evaluations_total"]) for row in rows)
        km = kaplan_meier(
            [(int(row["evaluation_time"]), bool(row["event_observed"])) for row in rows],
            horizon=max(int(row["simulation_budget"]) for row in rows),
        )
        summaries.append({
            "method": method, "runs": len(rows),
            "success_rate": sum(bool(row["is_feasible"]) for row in rows) / len(rows),
            "median_best_objective": median(objectives) if objectives else None,
            "mean_best_objective": fmean(objectives) if objectives else None,
            "std_best_objective": pstdev(objectives) if objectives else None,
            "median_simulations_to_first_feasible": median(firsts) if firsts else None,
            "censored_runs": len(rows) - len(firsts),
            "median_constraint_violation": median(violations) if violations else None,
            "mean_runtime": fmean(float(row["total_runtime"]) for row in rows),
            "mean_simulation_time": fmean(simulation_times),
            "failure_rate": (sum(int(row["evaluations_failed"]) for row in rows) / total_evaluations if total_evaluations else None),
            "ngspice_failure_rate": fmean(float(row.get("ngspice_failure_rate", 0.0)) for row in rows),
            "analysis_error_rate": fmean(float(row.get("analysis_error_rate", 0.0)) for row in rows),
            "invalid_response_rate": fmean(float(row.get("invalid_response_rate", 0.0)) for row in rows),
            "bandwidth_right_censored_rate": fmean(float(row.get("bandwidth_right_censored_rate", 0.0)) for row in rows),
            "complete_exact_metric_rate": fmean(float(row.get("complete_exact_metric_rate", 0.0)) for row in rows),
            "ngspice_calls": sum(int(row["ngspice_calls"]) for row in rows),
            "event_observed_count": sum(bool(row["event_observed"]) for row in rows),
            "censored_count": sum(not bool(row["event_observed"]) for row in rows),
            "km_median_time_to_feasible": km.median_time_to_event,
            "rmst": km.rmst,
            "best_gain": max(best_gains) if best_gains else None,
            "best_bandwidth": max(best_bandwidths) if best_bandwidths else None,
            "best_bandwidth_lower_bound": max(best_bandwidth_bounds) if best_bandwidth_bounds else None,
            "best_power": min(best_powers) if best_powers else None,
        })
    return summaries


def _csv_value(field: str, value: Any) -> Any:
    if value is None:
        return ""
    if field in {"best_parameters", "best_metrics"}:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if isinstance(value, bool):
        return str(value).lower()
    return value


def write_table(path: str | Path, columns: tuple[str, ...], rows: Iterable[dict[str, Any]]) -> Path:
    destination = Path(path).resolve()
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for row in rows:
                writer.writerow({field: _csv_value(field, row.get(field)) for field in columns})
        temporary.replace(destination)
    except (OSError, TypeError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise ResearchExperimentError(f"failed to write baseline CSV '{destination}': {exc}") from exc
    return destination
