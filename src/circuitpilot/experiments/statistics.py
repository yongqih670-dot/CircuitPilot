"""Run-level and method-level statistics derived from evaluation CSV evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import fmean, median, pstdev
from typing import Any, Iterable

from circuitpilot.exceptions import ResearchExperimentError


RESULT_COLUMNS = (
    "method", "seed", "run_id", "output_directory", "simulation_budget",
    "evaluations_total", "evaluations_success", "evaluations_failed", "ngspice_calls",
    "best_objective", "best_parameters", "best_metrics", "is_feasible",
    "first_feasible_iteration", "simulations_to_first_feasible",
    "total_runtime", "mean_simulation_time",
)

SUMMARY_COLUMNS = (
    "method", "runs", "success_rate", "median_best_objective",
    "mean_best_objective", "std_best_objective",
    "median_simulations_to_first_feasible", "censored_runs",
    "mean_runtime", "failure_rate",
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
    try:
        manifest = json.loads((directory / "research_manifest.json").read_text(encoding="utf-8"))
        budget = int(manifest["configuration"]["experiment"]["simulation_budget"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ResearchExperimentError(f"cannot read run manifest '{directory}': {exc}") from exc
    successful = [row for row in rows if row["simulation_status"] == "success"]
    best = min(successful, key=lambda row: (float(row["constraint_violation"]), float(row["objective_value"]), row["iteration"])) if successful else None
    first_feasible = next((row for row in rows if row["is_feasible"]), None)
    return {
        "method": rows[0]["method"], "seed": rows[0]["seed"], "run_id": rows[0]["run_id"],
        "output_directory": str(directory), "simulation_budget": budget,
        "evaluations_total": len(rows), "evaluations_success": len(successful),
        "evaluations_failed": len(rows) - len(successful),
        "ngspice_calls": sum(bool(row["ngspice_called"]) for row in rows),
        "best_objective": None if best is None else best["objective_value"],
        "best_parameters": None if best is None else best["parameters"],
        "best_metrics": None if best is None else best["raw_metrics"],
        "is_feasible": first_feasible is not None,
        "first_feasible_iteration": None if first_feasible is None else first_feasible["iteration"],
        "simulations_to_first_feasible": None if first_feasible is None else first_feasible["iteration"],
        "total_runtime": max(row["total_elapsed_time"] for row in rows),
        "mean_simulation_time": fmean(row["simulation_time"] for row in rows),
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
        total_evaluations = sum(int(row["evaluations_total"]) for row in rows)
        summaries.append({
            "method": method, "runs": len(rows),
            "success_rate": sum(bool(row["is_feasible"]) for row in rows) / len(rows),
            "median_best_objective": median(objectives) if objectives else None,
            "mean_best_objective": fmean(objectives) if objectives else None,
            "std_best_objective": pstdev(objectives) if objectives else None,
            "median_simulations_to_first_feasible": median(firsts) if firsts else None,
            "censored_runs": len(rows) - len(firsts),
            "mean_runtime": fmean(float(row["total_runtime"]) for row in rows),
            "failure_rate": (sum(int(row["evaluations_failed"]) for row in rows) / total_evaluations if total_evaluations else None),
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
