"""Checkpointed parallel suites and fairness validation for Task 9."""

from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable

from circuitpilot.exceptions import FairComparisonError, ResearchExperimentError
from circuitpilot.experiments.task9_runner import Task9RunDefinition, execute_task9_run
from circuitpilot.task7_protocol import METHODS, TASK7_BENCHMARK_HASH
from circuitpilot.task9_protocol import (
    FORMAL_CANDIDATE_BUDGET,
    FORMAL_SIMULATION_TIME_BUDGET_SECONDS,
    FORMAL_SIMULATION_TIME_CANDIDATE_CAP,
    PVT_BENCHMARK_HASH,
    SMOKE_CANDIDATE_BUDGET,
    TASK9_PROTOCOL_HASH,
)


DESIGNS = {
    "smoke": {
        "seeds": (0, 1, 2),
        "candidate_budget": SMOKE_CANDIDATE_BUDGET,
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
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _stored_run_directory(suite: Path, run_directory: Path) -> str:
    """Store suite-relative run paths so committed evidence remains portable."""
    try:
        return run_directory.resolve().relative_to(suite.resolve()).as_posix()
    except ValueError:
        return str(run_directory.resolve())


def _resolved_run_directory(suite: Path, stored: str) -> Path:
    path = Path(stored)
    return path.resolve() if path.is_absolute() else (suite / path).resolve()


def _git_provenance(workspace: Path) -> dict[str, Any]:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=workspace, check=True, text=True, capture_output=True
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=workspace, check=True, text=True, capture_output=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ResearchExperimentError(f"cannot collect Task 9 git provenance: {exc}") from exc
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
    found = {(row["policy"], row["method"], int(row["seed"])) for row in summaries}
    if found != expected or len(summaries) != len(expected):
        raise FairComparisonError("Task 9 suite cell coverage is incomplete")
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
                name for name in full_identity if full_identity[name] != hierarchical_identity[name]
            }
            if differences != {"policy_hash"}:
                raise FairComparisonError(
                    f"Task 9 fairness identity drifted for {method}/seed_{seed}: {sorted(differences)}"
                )
            paired_checks.append(
                {"method": method, "seed": seed, "only_allowed_difference": "policy_hash"}
            )
    for row in summaries:
        if (
            not row["completed"]
            or row["task7_benchmark_hash"] != TASK7_BENCHMARK_HASH
            or row["task9_protocol_hash"] != TASK9_PROTOCOL_HASH
            or row["pvt_benchmark_hash"] != PVT_BENCHMARK_HASH
            or int(row["process_calls"])
            != int(row["op_calls"]) + int(row["ac_calls"]) + int(row["transient_calls"])
            or int(row["op_calls"]) != int(row["corners_started"])
        ):
            raise FairComparisonError(f"Task 9 cost/identity check failed for {row['experiment_id']}")
        candidates = int(row["candidate_count"])
        if row["policy"] == "full" and (
            int(row["corners_started"]) != 15 * candidates
            or int(row["corners_completed"]) != 15 * candidates
            or int(row["op_calls"]) != 15 * candidates
            or int(row["ac_calls"]) != 15 * candidates
            or int(row["transient_calls"]) != 15 * candidates
            or int(row["process_calls"]) != 45 * candidates
        ):
            raise FairComparisonError("Full-PVT did not execute every stage/corner")
        if row["policy"] == "hierarchical" and not (
            int(row["transient_calls"]) <= int(row["ac_calls"]) <= int(row["op_calls"])
            and int(row["corners_completed"]) == int(row["transient_calls"])
        ):
            raise FairComparisonError("Hierarchical-PVT counters are not monotone")
        if design == "smoke" and row["policy"] == "hierarchical" and int(row["shadow_false_rejection_count"]) != 0:
            raise FairComparisonError("Task 9 smoke shadow audit found a false rejection")
        if design in {"smoke", "equal_candidate"}:
            if candidates != int(DESIGNS[design]["candidate_budget"]):
                raise FairComparisonError("Task 9 equal-candidate cell stopped at wrong budget")
        else:
            budget = float(DESIGNS[design]["simulation_time_budget_seconds"])
            cap = int(DESIGNS[design]["candidate_cap"])
            if float(row["accumulated_ngspice_seconds"]) < budget and candidates < cap:
                raise FairComparisonError("Task 9 equal-time cell stopped before budget/cap")
    return {
        "status": "pass",
        "design": design,
        "cell_count": len(summaries),
        "methods": list(methods),
        "policies": list(POLICIES),
        "seeds": list(seeds),
        "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
        "task9_protocol_hash": TASK9_PROTOCOL_HASH,
        "pvt_benchmark_hash": PVT_BENCHMARK_HASH,
        "paired_identity_checks": paired_checks,
        "smoke_shadow_false_rejection_count": sum(
            int(row["shadow_false_rejection_count"]) for row in summaries
        ),
    }


def _consolidate_evaluations(summaries: list[dict[str, Any]], destination: Path) -> None:
    rows: list[dict[str, Any]] = []
    fieldnames: list[str] | None = None
    for summary in summaries:
        with (Path(summary["_run_directory"]) / "evaluations.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            reader = csv.DictReader(handle)
            if fieldnames is None:
                fieldnames = list(reader.fieldnames or [])
            rows.extend(reader)
    if fieldnames is None:
        raise ResearchExperimentError("Task 9 suite has no evaluation rows")
    temporary = destination.with_name(f".{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(destination)


def run_task9_suite(
    *,
    base_config_path: str | Path,
    design: str,
    output_root: str | Path,
    methods: Iterable[str] = METHODS,
    seeds: Iterable[int] | None = None,
    workers: int = 4,
) -> Path:
    if design not in DESIGNS:
        raise ValueError(f"unknown Task 9 design '{design}'")
    if workers <= 0:
        raise ValueError("Task 9 workers must be positive")
    suite = Path(output_root).resolve()
    protocol = DESIGNS[design]
    selected_methods = tuple(methods)
    selected_seeds = tuple(protocol["seeds"] if seeds is None else seeds)
    provenance = _git_provenance(Path.cwd().resolve())
    if design != "smoke" and provenance["dirty"]:
        try:
            allowed = suite.relative_to(Path.cwd().resolve()).as_posix().rstrip("/") + "/"
        except ValueError:
            allowed = ""
        unexpected = [
            line
            for line in provenance["status_porcelain"].splitlines()
            if not line[3:].replace("\\", "/").startswith(allowed)
        ]
        if unexpected:
            raise ResearchExperimentError(
                "formal Task 9 requires committed source; unexpected changes: " + "; ".join(unexpected)
            )
    suite.mkdir(parents=True, exist_ok=True)
    state_path = suite / "suite_state.json"
    identity = {
        "schema_version": "task9_suite_state_v1",
        "design": design,
        "methods": list(selected_methods),
        "policies": list(POLICIES),
        "seeds": list(selected_seeds),
        "candidate_budget": protocol["candidate_budget"],
        "simulation_time_budget_seconds": protocol["simulation_time_budget_seconds"],
        "candidate_cap": protocol["candidate_cap"],
        "task9_protocol_hash": TASK9_PROTOCOL_HASH,
        "pvt_benchmark_hash": PVT_BENCHMARK_HASH,
    }
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for key, value in identity.items():
            if state.get(key) != value:
                raise ResearchExperimentError(f"resumed Task 9 suite changed at {key}")
        commits = list(state.get("git_commits", []))
        if provenance["commit"] not in commits:
            commits.append(provenance["commit"])
        state["git_commits"] = commits
    else:
        state = {
            **identity,
            "git_commits": [provenance["commit"]],
            "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            "status": "incomplete",
            "cells": {},
        }
    _atomic_json(state_path, state)
    definitions = {
        f"{policy}/{method}/seed_{seed}": Task9RunDefinition(
            base_config_path=Path(base_config_path).resolve(),
            method=method,
            policy=policy,
            seed=seed,
            experiment_design=design,
            output_root=suite / "runs",
            candidate_budget=protocol["candidate_budget"],
            simulation_time_budget_seconds=protocol["simulation_time_budget_seconds"],
            candidate_cap=protocol["candidate_cap"],
            shadow_audit=design == "smoke" and policy == "hierarchical",
        )
        for policy in POLICIES
        for method in selected_methods
        for seed in selected_seeds
    }
    for run_directory in (suite / "runs").glob("*"):
        definition_path = run_directory / "task9_run_definition.json"
        summary_path = run_directory / "summary" / "experiment_summary.json"
        if not definition_path.is_file() or not summary_path.is_file():
            continue
        try:
            recovered_definition = json.loads(definition_path.read_text(encoding="utf-8"))
            recovered_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        key = f"{recovered_definition.get('policy')}/{recovered_definition.get('method')}/seed_{recovered_definition.get('seed')}"
        expected_definition = definitions.get(key)
        if expected_definition and recovered_definition == expected_definition.semantic_dict() and recovered_summary.get("completed"):
            state["cells"][key] = {
                "status": "success",
                "run_directory": _stored_run_directory(suite, run_directory),
                "run_id": recovered_summary["run_id"],
            }
    _atomic_json(state_path, state)
    pending = {
        key: definition
        for key, definition in definitions.items()
        if state["cells"].get(key, {}).get("status") != "success"
    }

    def execute(key: str, definition: Task9RunDefinition):
        cell = state["cells"].get(key)
        print(f"starting {key}", flush=True)
        return execute_task9_run(
            definition,
            resume_directory=(
                None
                if cell is None
                else _resolved_run_directory(suite, cell["run_directory"])
            ),
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(execute, key, definition): key for key, definition in pending.items()}
        for future in as_completed(futures):
            key = futures[future]
            run_directory, summary = future.result()
            state["cells"][key] = {
                "status": "success" if summary["completed"] else "incomplete",
                "run_directory": _stored_run_directory(suite, run_directory),
                "run_id": summary["run_id"],
            }
            _atomic_json(state_path, state)
            print(f"completed {key}", flush=True)
            if not summary["completed"]:
                raise ResearchExperimentError(f"Task 9 cell {key} stopped early")
    summaries = []
    for cell in state["cells"].values():
        run_directory = _resolved_run_directory(suite, cell["run_directory"])
        summary = json.loads(
            (run_directory / "summary" / "experiment_summary.json").read_text(encoding="utf-8")
        )
        summary["_run_directory"] = str(run_directory)
        summaries.append(summary)
    summaries.sort(key=lambda row: (row["policy"], row["method"], int(row["seed"])))
    fairness = validate_fairness(
        summaries, design=design, methods=selected_methods, seeds=selected_seeds
    )
    fairness["execution_commits"] = state["git_commits"]
    public_summaries = [
        {name: value for name, value in summary.items() if name != "_run_directory"}
        for summary in summaries
    ]
    _atomic_json(suite / "cell_summaries.json", public_summaries)
    _atomic_json(suite / "fairness_validation.json", fairness)
    _consolidate_evaluations(summaries, suite / "evaluations.csv")
    state["status"] = "success"
    state["completed_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    _atomic_json(state_path, state)
    return suite
