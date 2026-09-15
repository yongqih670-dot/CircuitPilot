"""Checkpointed Task 7 suites, fairness validation, survival, and cost summaries."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import mean, median
import subprocess
from typing import Any, Iterable

from circuitpilot.exceptions import FairComparisonError, ResearchExperimentError
from circuitpilot.experiments.task7_runner import (
    Task7RunDefinition,
    execute_task7_run,
)
from circuitpilot.run_directory import generate_run_id
from circuitpilot.task7_protocol import (
    METHODS,
    TASK7_BENCHMARK_HASH,
    TASK7_COMPONENT_HASHES,
    TASK7_SEARCH_SPACE_HASH,
    protocol_family_hash,
)


DESIGNS = {
    "smoke": {"seeds": (0, 1, 2), "candidate_budget": 25},
    "formal": {"seeds": tuple(range(10)), "candidate_budget": 50},
}


def _atomic_json(path: Path, payload: Any) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _git_provenance(workspace: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ResearchExperimentError(f"cannot collect Task 7 git provenance: {exc}") from exc
    return {"commit": commit, "dirty": bool(status), "status_porcelain": status}


def load_summary(directory: str | Path) -> dict[str, Any]:
    path = Path(directory).resolve() / "summary" / "experiment_summary.json"
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResearchExperimentError(f"cannot load Task 7 summary '{path}': {exc}") from exc
    result["_run_directory"] = str(path.parents[1])
    return result


def load_evaluations(directory: str | Path) -> list[dict[str, Any]]:
    path = Path(directory).resolve() / "evaluations.csv"
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise ResearchExperimentError(f"cannot load Task 7 evaluations: {exc}") from exc
    for row in rows:
        for name in (
            "metrics",
            "analysis_errors",
            "constraint_components",
            "parameters",
        ):
            row[name] = json.loads(row[name])
        row["iteration"] = int(row["iteration"])
        row["is_feasible"] = row["is_feasible"] == "true"
        row["event_observed"] = row["event_observed"] == "true"
        for name in (
            "op_runtime_seconds",
            "ac_runtime_seconds",
            "transient_runtime_seconds",
            "wall_clock_seconds",
        ):
            row[name] = float(row[name])
    return rows


def validate_fairness(
    summaries: list[dict[str, Any]],
    *,
    methods: tuple[str, ...],
    seeds: tuple[int, ...],
    design: str,
    candidate_budget: int,
) -> dict[str, Any]:
    expected = {(method, seed) for method in methods for seed in seeds}
    found = {(row["method"], int(row["seed"])) for row in summaries}
    if found != expected or len(summaries) != len(expected):
        raise FairComparisonError("Task 7 suite cell coverage is incomplete")
    for row in summaries:
        if (
            not row.get("completed")
            or row.get("experiment_design") != design
            or int(row.get("candidate_budget", -1)) != candidate_budget
            or row.get("task7_benchmark_hash") != TASK7_BENCHMARK_HASH
            or row.get("task7_search_space_hash") != TASK7_SEARCH_SPACE_HASH
            or row.get("task7_protocol_family_hash") != protocol_family_hash()
            or row.get("component_hashes") != TASK7_COMPONENT_HASHES
            or int(row.get("candidate_evaluations", -1)) != candidate_budget
            or int(row.get("ngspice_process_calls", -1)) != 3 * candidate_budget
            or int(row.get("op_calls", -1)) != candidate_budget
            or int(row.get("ac_calls", -1)) != candidate_budget
            or int(row.get("transient_calls", -1)) != candidate_budget
            or int(row.get("high_fidelity_analysis_calls", -1))
            != 3 * candidate_budget
            or int(row.get("screening_calls", -1)) != 0
        ):
            raise FairComparisonError(
                f"Task 7 fairness/cost identity failed for {row.get('experiment_id')}"
            )
    return {
        "status": "pass",
        "cell_count": len(summaries),
        "design": design,
        "methods": list(methods),
        "seeds": list(seeds),
        "candidate_budget": candidate_budget,
        "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
        "task7_search_space_hash": TASK7_SEARCH_SPACE_HASH,
        "task7_protocol_family_hash": protocol_family_hash(),
        "component_hashes": dict(TASK7_COMPONENT_HASHES),
        "full_only_cost_identity": "each row 1 candidate, 3 processes, 1 OP, 1 AC, 1 transient",
    }


def _kaplan_meier(
    summaries: list[dict[str, Any]], budget: int
) -> tuple[list[dict[str, Any]], float, int | None]:
    curve = [{"candidate": 0, "event_free_probability": 1.0, "at_risk": len(summaries), "events": 0}]
    survival = 1.0
    for candidate in range(1, budget + 1):
        at_risk = sum(
            not row["event_observed"]
            or int(row["candidate_time_to_first_feasible"]) >= candidate
            for row in summaries
        )
        events = sum(
            row["event_observed"]
            and int(row["candidate_time_to_first_feasible"]) == candidate
            for row in summaries
        )
        if at_risk:
            survival *= 1.0 - events / at_risk
        curve.append(
            {
                "candidate": candidate,
                "event_free_probability": survival,
                "at_risk": at_risk,
                "events": events,
            }
        )
    rmst = sum(float(item["event_free_probability"]) for item in curve[:-1])
    median_time = next(
        (
            int(item["candidate"])
            for item in curve[1:]
            if float(item["event_free_probability"]) <= 0.5
        ),
        None,
    )
    return curve, rmst, median_time


def write_statistics(
    summaries: list[dict[str, Any]], output: Path, candidate_budget: int
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    method_payload: dict[str, Any] = {}
    evaluation_cache: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for row in summaries:
        evaluation_cache[(row["method"], int(row["seed"]))] = load_evaluations(
            row["_run_directory"]
        )
    for method in METHODS:
        method_rows = [row for row in summaries if row["method"] == method]
        curve, rmst, median_time = _kaplan_meier(method_rows, candidate_budget)
        evaluations = [
            item
            for row in method_rows
            for item in evaluation_cache[(method, int(row["seed"]))]
        ]
        feasible_power = [
            float(item["metrics"]["dc_power_w"])
            for item in evaluations
            if item["is_feasible"] and item["metrics"].get("dc_power_w") is not None
        ]
        status_counts: dict[str, dict[str, int]] = {}
        for field in (
            "simulation_status",
            "ugf_status",
            "phase_margin_status",
            "positive_slew_status",
            "negative_slew_status",
        ):
            values: dict[str, int] = {}
            for item in evaluations:
                key = str(item[field])
                values[key] = values.get(key, 0) + 1
            status_counts[field] = values
        method_payload[method] = {
            "run_count": len(method_rows),
            "event_count": sum(bool(row["event_observed"]) for row in method_rows),
            "success_rate": mean(
                float(bool(row["event_observed"])) for row in method_rows
            ),
            "candidate_rmst": rmst,
            "median_time_to_event": median_time,
            "kaplan_meier": curve,
            "best_feasible_power_w": {
                "count": len(feasible_power),
                "median": None if not feasible_power else median(feasible_power),
                "minimum": None if not feasible_power else min(feasible_power),
            },
            "status_counts": status_counts,
        }
    pairwise = []
    for left_index, left in enumerate(METHODS):
        for right in METHODS[left_index + 1 :]:
            left_rows = {int(row["seed"]): row for row in summaries if row["method"] == left}
            right_rows = {int(row["seed"]): row for row in summaries if row["method"] == right}
            seeds = sorted(set(left_rows) & set(right_rows))
            restricted_differences = []
            success_differences = []
            for seed in seeds:
                left_row, right_row = left_rows[seed], right_rows[seed]
                left_time = (
                    int(left_row["candidate_time_to_first_feasible"])
                    if left_row["event_observed"]
                    else candidate_budget
                )
                right_time = (
                    int(right_row["candidate_time_to_first_feasible"])
                    if right_row["event_observed"]
                    else candidate_budget
                )
                restricted_differences.append(left_time - right_time)
                success_differences.append(
                    int(bool(left_row["event_observed"]))
                    - int(bool(right_row["event_observed"]))
                )
            pairwise.append(
                {
                    "left": left,
                    "right": right,
                    "paired_seeds": seeds,
                    "mean_restricted_time_difference_left_minus_right": mean(
                        restricted_differences
                    ),
                    "mean_success_difference_left_minus_right": mean(
                        success_differences
                    ),
                }
            )
    all_evaluations = [
        item for values in evaluation_cache.values() for item in values
    ]
    cost_profile = {}
    for name in (
        "op_runtime_seconds",
        "ac_runtime_seconds",
        "transient_runtime_seconds",
        "wall_clock_seconds",
    ):
        values = sorted(float(row[name]) for row in all_evaluations)
        cost_profile[name] = {
            "count": len(values),
            "median": median(values),
            "mean": mean(values),
            "p90": values[min(len(values) - 1, int(0.9 * len(values)))],
        }
    _atomic_json(
        output / "survival_statistics.json",
        {
            "candidate_budget": candidate_budget,
            "methods": method_payload,
            "pairwise": pairwise,
            "interpretation": "descriptive paired-seed estimates",
        },
    )
    _atomic_json(output / "per_analysis_cost_profile.json", cost_profile)


def run_task7_suite(
    *,
    base_config_path: str | Path,
    design: str,
    output_root: str | Path,
    resume_suite: str | Path | None = None,
    methods: Iterable[str] = METHODS,
    seeds: Iterable[int] | None = None,
) -> Path:
    if design not in DESIGNS:
        raise ValueError(f"unknown Task 7 design '{design}'")
    protocol = DESIGNS[design]
    selected_methods = tuple(methods)
    selected_seeds = tuple(protocol["seeds"] if seeds is None else seeds)
    budget = int(protocol["candidate_budget"])
    provenance = _git_provenance(Path.cwd().resolve())
    if design == "formal" and provenance["dirty"]:
        raise ResearchExperimentError("formal Task 7 requires a clean committed worktree")
    identity = {
        "schema_version": 1,
        "design": design,
        "methods": list(selected_methods),
        "seeds": list(selected_seeds),
        "candidate_budget": budget,
        "task7_protocol_family_hash": protocol_family_hash(),
        "git_commit": provenance["commit"],
    }
    if resume_suite is None:
        root = Path(output_root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        suite = root / f"{design}-{generate_run_id()}"
        suite.mkdir(exist_ok=False)
        state: dict[str, Any] = {
            **identity,
            "created_at_utc": datetime.now(timezone.utc).isoformat(
                timespec="microseconds"
            ),
            "status": "incomplete",
            "cells": {},
        }
        _atomic_json(suite / "suite_state.json", state)
    else:
        suite = Path(resume_suite).resolve()
        state = json.loads((suite / "suite_state.json").read_text(encoding="utf-8"))
        for key, value in identity.items():
            if state.get(key) != value:
                raise ResearchExperimentError(f"resumed Task 7 suite changed at {key}")

    for method in selected_methods:
        for seed in selected_seeds:
            key = f"{method}/seed_{seed}"
            cell = state["cells"].get(key)
            if cell and cell.get("status") == "success":
                continue
            print(f"starting {key}", flush=True)
            result = execute_task7_run(
                Task7RunDefinition(
                    base_config_path=Path(base_config_path).resolve(),
                    method=method,
                    seed=seed,
                    candidate_budget=budget,
                    experiment_design=design,
                    output_root=suite / "runs",
                ),
                resume_directory=None if cell is None else cell["run_directory"],
            )
            state["cells"][key] = {
                "status": "success" if result.completed else "incomplete",
                "run_directory": str(result.output_directory),
                "run_id": result.run_id,
            }
            _atomic_json(suite / "suite_state.json", state)
            if not result.completed:
                raise ResearchExperimentError(f"Task 7 cell {key} stopped early")

    summaries = [load_summary(cell["run_directory"]) for cell in state["cells"].values()]
    fairness = validate_fairness(
        summaries,
        methods=selected_methods,
        seeds=selected_seeds,
        design=design,
        candidate_budget=budget,
    )
    _atomic_json(suite / "fairness_validation.json", fairness)
    write_statistics(summaries, suite / "statistics", budget)
    state["status"] = "success"
    state["completed_at_utc"] = datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
    )
    _atomic_json(suite / "suite_state.json", state)
    return suite
