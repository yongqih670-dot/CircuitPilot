"""Checkpointed Task 6 suite execution."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from typing import Any, Iterable

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.task6_runner import (
    Task6RunDefinition,
    execute_task6_run,
)
from circuitpilot.experiments.task6_statistics import (
    load_task6_summary,
    validate_task6_fairness,
    write_task6_statistics,
)
from circuitpilot.run_directory import generate_run_id
from circuitpilot.task6_protocol import (
    FULL_POLICY,
    METHODS,
    SCREENED_POLICY,
    evaluation_policy_family_hash,
)


DESIGNS: dict[str, dict[str, Any]] = {
    "smoke": {
        "seeds": (0, 1, 2), "candidate_cap": 25,
        "expensive_ac_budget": None,
    },
    "formal_equal_candidate": {
        "seeds": tuple(range(10)), "candidate_cap": 100,
        "expensive_ac_budget": None,
    },
    "formal_equal_cost": {
        "seeds": tuple(range(10)), "candidate_cap": 300,
        "expensive_ac_budget": 200,
    },
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
            ["git", "rev-parse", "HEAD"], cwd=workspace, check=True,
            text=True, capture_output=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=workspace, check=True,
            text=True, capture_output=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ResearchExperimentError(f"cannot collect git provenance: {exc}") from exc
    return {"commit": commit, "dirty": bool(status), "status_porcelain": status}


def run_task6_suite(
    *, base_config_path: str | Path, design: str, output_root: str | Path,
    resume_suite: str | Path | None = None,
    methods: Iterable[str] = METHODS,
    policies: Iterable[str] = (FULL_POLICY, SCREENED_POLICY),
    seeds: Iterable[int] | None = None,
) -> Path:
    """Run all frozen cells and checkpoint suite_state.json after each cell."""
    if design not in DESIGNS:
        raise ValueError(f"unknown Task 6 design '{design}'")
    protocol = DESIGNS[design]
    selected_methods = tuple(methods)
    selected_policies = tuple(policies)
    selected_seeds = tuple(protocol["seeds"] if seeds is None else seeds)
    provenance = _git_provenance(Path.cwd().resolve())
    if design.startswith("formal_") and provenance["dirty"]:
        raise ResearchExperimentError(
            "formal Task 6 suites require a clean committed worktree"
        )
    identity = {
        "schema_version": 1, "design": design,
        "methods": list(selected_methods), "policies": list(selected_policies),
        "seeds": list(selected_seeds),
        "candidate_cap": int(protocol["candidate_cap"]),
        "expensive_ac_budget": protocol["expensive_ac_budget"],
        "task6_policy_family_hash": evaluation_policy_family_hash(),
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
            "status": "incomplete", "cells": {},
        }
        _atomic_json(suite / "suite_state.json", state)
    else:
        suite = Path(resume_suite).resolve()
        try:
            state = json.loads(
                (suite / "suite_state.json").read_text(encoding="utf-8")
            )
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ResearchExperimentError(f"invalid resumed Task 6 suite: {exc}") from exc
        for key, value in identity.items():
            if state.get(key) != value:
                raise ResearchExperimentError(
                    f"resumed suite identity changed at '{key}'"
                )

    for method in selected_methods:
        for policy in selected_policies:
            for seed in selected_seeds:
                key = f"{method}/{policy}/seed_{seed}"
                cell = state["cells"].get(key)
                if cell and cell.get("status") == "success":
                    continue
                definition = Task6RunDefinition(
                    base_config_path=Path(base_config_path).resolve(),
                    method=method, evaluation_policy=policy, seed=seed,
                    candidate_cap=int(protocol["candidate_cap"]),
                    expensive_ac_budget=protocol["expensive_ac_budget"],
                    experiment_design=design, output_root=suite / "runs",
                )
                result = execute_task6_run(
                    definition,
                    resume_directory=(
                        None if cell is None else Path(cell["run_directory"])
                    ),
                )
                state["cells"][key] = {
                    "status": "success" if result.completed else "incomplete",
                    "run_directory": str(result.output_directory),
                    "run_id": result.run_id,
                }
                _atomic_json(suite / "suite_state.json", state)
                if not result.completed:
                    raise ResearchExperimentError(
                        f"Task 6 cell '{key}' stopped before its frozen budget"
                    )

    summaries = [
        load_task6_summary(cell["run_directory"])
        for cell in state["cells"].values()
    ]
    fairness = validate_task6_fairness(
        summaries, expected_methods=selected_methods,
        expected_policies=selected_policies, expected_seeds=selected_seeds,
        candidate_cap=int(protocol["candidate_cap"]),
        expensive_ac_budget=protocol["expensive_ac_budget"],
        experiment_design=design,
    )
    _atomic_json(suite / "fairness_validation.json", fairness)
    write_task6_statistics(summaries, suite / "statistics")
    state["status"] = "success"
    state["completed_at_utc"] = datetime.now(timezone.utc).isoformat(
        timespec="microseconds"
    )
    _atomic_json(suite / "suite_state.json", state)
    return suite
