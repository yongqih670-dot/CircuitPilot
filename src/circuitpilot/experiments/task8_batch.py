"""Checkpointed parallel suites and fairness validation for Task 8."""

from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable

from circuitpilot.exceptions import FairComparisonError, ResearchExperimentError
from circuitpilot.experiments.task8_runner import (
    TASK8_PROTOCOL_HASH,
    Task8RunDefinition,
    execute_task8_run,
)
from circuitpilot.task7_protocol import METHODS, TASK7_BENCHMARK_HASH
from circuitpilot.task8_protocol import (
    FORMAL_CANDIDATE_BUDGET,
    FORMAL_SIMULATION_TIME_BUDGET_SECONDS,
    FORMAL_SIMULATION_TIME_CANDIDATE_CAP,
)


DESIGNS = {
    "smoke": {
        "seeds": (0, 1, 2),
        "candidate_budget": 25,
        "simulation_time_budget_seconds": None,
        "candidate_cap": None,
    },
    "equal_candidate": {
        "seeds": tuple(range(10)),
        "candidate_budget": FORMAL_CANDIDATE_BUDGET,
        "simulation_time_budget_seconds": None,
        "candidate_cap": None,
    },
    "equal_simulation_time": {
        "seeds": tuple(range(10)),
        "candidate_budget": None,
        "simulation_time_budget_seconds": FORMAL_SIMULATION_TIME_BUDGET_SECONDS,
        "candidate_cap": FORMAL_SIMULATION_TIME_CANDIDATE_CAP,
    },
}
POLICIES = ("full", "hierarchical")


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        raise ResearchExperimentError(f"cannot collect Task 8 git provenance: {exc}") from exc
    return {"commit": commit, "dirty": bool(status), "status_porcelain": status}


def validate_fairness(
    summaries: list[dict[str, Any]],
    *,
    design: str,
    methods: tuple[str, ...],
    seeds: tuple[int, ...],
) -> dict[str, Any]:
    expected = {
        (policy, method, seed)
        for policy in POLICIES
        for method in methods
        for seed in seeds
    }
    found = {
        (row["policy"], row["method"], int(row["seed"])) for row in summaries
    }
    if found != expected or len(summaries) != len(expected):
        raise FairComparisonError("Task 8 suite cell coverage is incomplete")
    paired_checks = []
    for method in methods:
        for seed in seeds:
            pair = {
                row["policy"]: row
                for row in summaries
                if row["method"] == method and int(row["seed"]) == seed
            }
            full_identity = pair["full"]["fairness_identity"]
            hierarchical_identity = pair["hierarchical"]["fairness_identity"]
            differences = {
                name
                for name in full_identity
                if full_identity[name] != hierarchical_identity[name]
            }
            if differences != {"evaluation_policy_hash"}:
                raise FairComparisonError(
                    f"Task 8 fairness identity drifted for {method}/seed_{seed}: "
                    f"{sorted(differences)}"
                )
            paired_checks.append(
                {
                    "method": method,
                    "seed": seed,
                    "only_allowed_difference": "evaluation_policy_hash",
                }
            )
    for row in summaries:
        if (
            not row["completed"]
            or row["task7_benchmark_hash"] != TASK7_BENCHMARK_HASH
            or row["task8_protocol_hash"] != TASK8_PROTOCOL_HASH
            or int(row["ngspice_process_calls"])
            != int(row["logical_high_fidelity_calls"])
            or int(row["op_calls"]) != int(row["candidate_count"])
        ):
            raise FairComparisonError(
                f"Task 8 cost/identity check failed for {row['experiment_id']}"
            )
        candidates = int(row["candidate_count"])
        if row["policy"] == "full" and (
            int(row["ac_calls"]) != candidates
            or int(row["transient_calls"]) != candidates
            or int(row["ngspice_process_calls"]) != 3 * candidates
        ):
            raise FairComparisonError("Full policy did not execute all analyses")
        if row["policy"] == "hierarchical" and not (
            int(row["transient_calls"]) <= int(row["ac_calls"]) <= candidates
        ):
            raise FairComparisonError("Hierarchical stage counters are not monotone")
        if design == "smoke" and row["policy"] == "hierarchical":
            if int(row["shadow_false_rejection_count"]) != 0:
                raise FairComparisonError("smoke shadow audit found a false rejection")
        if design in {"smoke", "equal_candidate"}:
            expected_budget = int(DESIGNS[design]["candidate_budget"])
            if candidates != expected_budget:
                raise FairComparisonError("equal-candidate cell stopped at wrong budget")
        else:
            budget = float(DESIGNS[design]["simulation_time_budget_seconds"])
            cap = int(DESIGNS[design]["candidate_cap"])
            if (
                float(row["accumulated_ngspice_seconds"]) < budget
                and candidates < cap
            ):
                raise FairComparisonError("equal-time cell stopped before its budget")
    return {
        "status": "pass",
        "design": design,
        "cell_count": len(summaries),
        "methods": list(methods),
        "policies": list(POLICIES),
        "seeds": list(seeds),
        "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
        "task8_protocol_hash": TASK8_PROTOCOL_HASH,
        "paired_identity_checks": paired_checks,
        "smoke_shadow_false_rejection_count": sum(
            int(row["shadow_false_rejection_count"]) for row in summaries
        ),
    }


def _consolidate_evaluations(
    summaries: list[dict[str, Any]], destination: Path
) -> None:
    rows: list[dict[str, Any]] = []
    fieldnames: list[str] | None = None
    for summary in summaries:
        path = Path(summary["_run_directory"]) / "evaluations.csv"
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if fieldnames is None:
                fieldnames = list(reader.fieldnames or [])
            rows.extend(reader)
    if fieldnames is None:
        raise ResearchExperimentError("Task 8 suite has no evaluation rows")
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(destination)


def run_task8_suite(
    *,
    base_config_path: str | Path,
    design: str,
    output_root: str | Path,
    methods: Iterable[str] = METHODS,
    seeds: Iterable[int] | None = None,
    workers: int = 4,
) -> Path:
    if design not in DESIGNS:
        raise ValueError(f"unknown Task 8 design '{design}'")
    if workers <= 0:
        raise ValueError("Task 8 workers must be positive")
    protocol = DESIGNS[design]
    selected_methods = tuple(methods)
    selected_seeds = tuple(protocol["seeds"] if seeds is None else seeds)
    provenance = _git_provenance(Path.cwd().resolve())
    if design != "smoke" and provenance["dirty"]:
        raise ResearchExperimentError("formal Task 8 requires a clean committed worktree")
    suite = Path(output_root).resolve()
    suite.mkdir(parents=True, exist_ok=True)
    state_path = suite / "suite_state.json"
    identity = {
        "schema_version": 1,
        "design": design,
        "methods": list(selected_methods),
        "policies": list(POLICIES),
        "seeds": list(selected_seeds),
        "candidate_budget": protocol["candidate_budget"],
        "simulation_time_budget_seconds": protocol["simulation_time_budget_seconds"],
        "candidate_cap": protocol["candidate_cap"],
        "task8_protocol_hash": TASK8_PROTOCOL_HASH,
        "git_commit": provenance["commit"],
    }
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for key, value in identity.items():
            if state.get(key) != value:
                raise ResearchExperimentError(f"resumed Task 8 suite changed at {key}")
    else:
        state = {
            **identity,
            "created_at_utc": datetime.now(timezone.utc).isoformat(
                timespec="microseconds"
            ),
            "status": "incomplete",
            "cells": {},
        }
        _atomic_json(state_path, state)

    definitions: dict[str, Task8RunDefinition] = {}
    for policy in POLICIES:
        for method in selected_methods:
            for seed in selected_seeds:
                key = f"{policy}/{method}/seed_{seed}"
                definitions[key] = Task8RunDefinition(
                    base_config_path=Path(base_config_path).resolve(),
                    method=method,
                    policy=policy,
                    seed=seed,
                    experiment_design=design,
                    output_root=suite / "runs",
                    candidate_budget=protocol["candidate_budget"],
                    simulation_time_budget_seconds=protocol[
                        "simulation_time_budget_seconds"
                    ],
                    candidate_cap=protocol["candidate_cap"],
                    shadow_audit=design == "smoke" and policy == "hierarchical",
                )

    pending = {
        key: definition
        for key, definition in definitions.items()
        if state["cells"].get(key, {}).get("status") != "success"
    }

    def execute(key: str, definition: Task8RunDefinition):
        cell = state["cells"].get(key)
        print(f"starting {key}", flush=True)
        return execute_task8_run(
            definition,
            resume_directory=None if cell is None else cell["run_directory"],
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(execute, key, definition): key
            for key, definition in pending.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            run_directory, summary = future.result()
            state["cells"][key] = {
                "status": "success" if summary["completed"] else "incomplete",
                "run_directory": str(run_directory),
                "run_id": summary["run_id"],
            }
            _atomic_json(state_path, state)
            print(f"completed {key}", flush=True)
            if not summary["completed"]:
                raise ResearchExperimentError(f"Task 8 cell {key} stopped early")

    summaries: list[dict[str, Any]] = []
    for cell in state["cells"].values():
        path = Path(cell["run_directory"]) / "summary" / "experiment_summary.json"
        summary = json.loads(path.read_text(encoding="utf-8"))
        summary["_run_directory"] = cell["run_directory"]
        summaries.append(summary)
    summaries.sort(key=lambda row: (row["policy"], row["method"], int(row["seed"])))
    fairness = validate_fairness(
        summaries,
        design=design,
        methods=selected_methods,
        seeds=selected_seeds,
    )
    _atomic_json(suite / "cell_summaries.json", summaries)
    _atomic_json(suite / "fairness_validation.json", fairness)
    _consolidate_evaluations(summaries, suite / "evaluations.csv")
    state["status"] = "success"
    state["completed_at_utc"] = datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
    )
    _atomic_json(state_path, state)
    return suite
