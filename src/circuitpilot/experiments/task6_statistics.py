"""Task 6 fairness checks, survival summaries, paired effects, and plots."""

from __future__ import annotations

import csv
from collections import Counter
import json
from pathlib import Path
from statistics import fmean, median
from typing import Any, Iterable

import numpy as np

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.statistics import write_table
from circuitpilot.task6_protocol import (
    FULL_POLICY,
    SCREENED_POLICY,
    TASK5_BENCHMARK_HASH,
    evaluation_policy_family_hash,
    evaluation_policy_hash,
)


RUN_COLUMNS = (
    "experiment_design", "method", "evaluation_policy", "seed", "run_id",
    "output_directory", "candidate_cap", "expensive_ac_budget",
    "candidate_evaluations", "candidate_time_to_first_feasible",
    "candidate_censor_time", "expensive_ac_analysis_count",
    "expensive_ac_time_to_first_feasible", "expensive_ac_censor_time",
    "wall_time_to_first_feasible", "wall_time_censor_time", "event_observed",
    "evaluations_success", "evaluations_failed", "op_rejected_candidates",
    "full_evaluated_candidates", "physics_invalid_candidates",
    "feasible_candidates", "ngspice_process_calls", "dc_op_calls",
    "differential_ac_calls", "common_mode_ac_calls",
    "full_ac_candidate_count", "physical_analysis_calls", "total_runtime",
    "best_objective", "best_constraint_violation",
)
GROUP_COLUMNS = (
    "experiment_design", "method", "evaluation_policy", "runs",
    "success_rate", "events", "censored", "candidate_km_median",
    "candidate_rmst", "expensive_ac_km_median", "expensive_ac_rmst",
    "median_wall_time_to_first_feasible", "candidate_evaluations",
    "expensive_ac_analysis_count", "ac_analyses_avoided_vs_full_nominal",
    "percent_ac_saved_vs_full_nominal", "op_rejected_candidates",
    "full_evaluated_candidates", "physics_invalid_candidates",
    "feasible_candidates", "ngspice_process_calls", "physical_analysis_calls",
    "total_runtime",
)
SURVIVAL_COLUMNS = (
    "experiment_design", "method", "evaluation_policy", "time_axis", "time",
    "survival_probability", "at_risk", "events", "censored", "horizon",
    "rmst", "km_median_time_to_feasible",
)
PAIRED_COLUMNS = (
    "experiment_design", "method", "outcome", "direction", "pairs",
    "mean_difference", "median_difference", "ci95_low", "ci95_high",
    "paired_differences",
)
VIOLATION_COLUMNS = (
    "experiment_design", "method", "evaluation_policy", "violation_type",
    "count", "candidate_count", "invalid_candidate_count", "candidate_rate",
    "invalid_conditional_rate",
)
VIOLATION_ITERATION_COLUMNS = (
    "experiment_design", "method", "evaluation_policy", "iteration",
    "candidate_count", "invalid_count", "invalid_rate",
    "mean_violation_count", "mean_op_constraint_violation",
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResearchExperimentError(f"cannot read Task 6 JSON '{path}': {exc}") from exc
    if not isinstance(value, dict):
        raise ResearchExperimentError(f"Task 6 JSON must be an object: '{path}'")
    return value


def load_task6_summary(run_directory: str | Path) -> dict[str, Any]:
    directory = Path(run_directory).resolve()
    payload = _read_json(directory / "summary" / "experiment_summary.json")
    best = payload.get("best_result")
    return {
        **{column: payload.get(column) for column in RUN_COLUMNS},
        "output_directory": str(directory),
        "best_objective": None if best is None else best.get("objective_value"),
        "best_constraint_violation": (
            None if best is None else best.get("constraint_violation")
        ),
        "_task5_benchmark_hash": payload.get("task5_benchmark_hash"),
        "_evaluation_policy_hash": payload.get("evaluation_policy_hash"),
        "_task6_policy_family_hash": payload.get("task6_policy_family_hash"),
        "_completed": payload.get("completed"),
    }


def load_task6_evaluations(run_directory: str | Path) -> list[dict[str, Any]]:
    source = Path(run_directory).resolve() / "evaluations.csv"
    try:
        with source.open("r", encoding="utf-8", newline="") as stream:
            raw_rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise ResearchExperimentError(f"cannot read evaluations '{source}': {exc}") from exc
    rows = []
    try:
        for raw in raw_rows:
            rows.append({
                **raw,
                "seed": int(raw["seed"]),
                "iteration": int(raw["iteration"]),
                "physics_violation_count": int(raw["physics_violation_count"]),
                "physics_violation_types": tuple(
                    json.loads(raw["physics_violation_types"])
                ),
                "op_constraint_violation": (
                    None if raw["op_constraint_violation"] == ""
                    else float(raw["op_constraint_violation"])
                ),
                "raw_metrics": json.loads(raw["raw_metrics"]),
                "is_feasible": raw["is_feasible"].lower() == "true",
                "event_observed": raw["event_observed"].lower() == "true",
            })
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ResearchExperimentError(
            f"invalid Task 6 evaluation row in '{source}': {exc}"
        ) from exc
    return rows


def validate_task6_fairness(
    summaries: Iterable[dict[str, Any]], *, expected_methods: Iterable[str],
    expected_policies: Iterable[str], expected_seeds: Iterable[int],
    candidate_cap: int, expensive_ac_budget: int | None,
    experiment_design: str,
) -> dict[str, Any]:
    """Reject incomplete cells, identity drift, and incorrect cost semantics."""
    rows = list(summaries)
    expected = {
        (method, policy, seed) for method in expected_methods
        for policy in expected_policies for seed in expected_seeds
    }
    actual = {
        (str(row["method"]), str(row["evaluation_policy"]), int(row["seed"]))
        for row in rows
    }
    if actual != expected or len(rows) != len(expected):
        raise ResearchExperimentError("Task 6 suite cells are incomplete or duplicated")
    for row in rows:
        policy = str(row["evaluation_policy"])
        if (
            row["_completed"] is not True
            or row["experiment_design"] != experiment_design
            or int(row["candidate_cap"]) != candidate_cap
            or row["expensive_ac_budget"] != expensive_ac_budget
            or row["_task5_benchmark_hash"] != TASK5_BENCHMARK_HASH
            or row["_evaluation_policy_hash"] != evaluation_policy_hash(policy)
            or row["_task6_policy_family_hash"] != evaluation_policy_family_hash()
        ):
            raise ResearchExperimentError("Task 6 fairness identity mismatch")
        candidates = int(row["candidate_evaluations"])
        ac_calls = int(row["expensive_ac_analysis_count"])
        if expensive_ac_budget is None and candidates != candidate_cap:
            raise ResearchExperimentError("equal-candidate run missed its cap")
        if (
            expensive_ac_budget is not None
            and candidates != candidate_cap
            and ac_calls != expensive_ac_budget
        ):
            raise ResearchExperimentError("equal-cost run stopped early")
        if ac_calls > (expensive_ac_budget or 2 * candidate_cap):
            raise ResearchExperimentError("Task 6 AC budget was exceeded")
        if policy == FULL_POLICY and any((
            int(row["ngspice_process_calls"]) != candidates,
            int(row["dc_op_calls"]) != candidates,
            int(row["differential_ac_calls"]) != candidates,
            int(row["common_mode_ac_calls"]) != candidates,
            int(row["full_ac_candidate_count"]) != candidates,
            int(row["physical_analysis_calls"]) != 2 * candidates,
        )):
            raise ResearchExperimentError("Full policy cost accounting drifted")
        full_ac = int(row["full_ac_candidate_count"])
        if policy == SCREENED_POLICY and any((
            int(row["dc_op_calls"]) != candidates,
            int(row["differential_ac_calls"]) != full_ac,
            int(row["common_mode_ac_calls"]) != full_ac,
            int(row["ngspice_process_calls"]) != candidates + full_ac,
            int(row["physical_analysis_calls"]) != candidates + full_ac,
        )):
            raise ResearchExperimentError("Screened policy cost accounting drifted")
    return {
        "status": "passed", "experiment_design": experiment_design,
        "cell_count": len(rows), "task5_benchmark_hash": TASK5_BENCHMARK_HASH,
        "task6_policy_family_hash": evaluation_policy_family_hash(),
        "candidate_cap": candidate_cap,
        "expensive_ac_budget": expensive_ac_budget,
    }


def _km(
    observations: list[tuple[int, bool]], horizon: int
) -> tuple[list[dict[str, Any]], float, int | None]:
    """Kaplan-Meier allowing a zero-cost censored observation."""
    if not observations or horizon <= 0:
        raise ValueError("invalid Task 6 survival inputs")
    if any(time < 0 or time > horizon for time, _ in observations):
        raise ValueError("Task 6 survival time is outside its horizon")
    survival, at_risk, last_time, rmst = 1.0, len(observations), 0, 0.0
    median_time = None
    points = []
    for time in sorted({value for value, _ in observations}):
        rmst += survival * (time - last_time)
        events = sum(value == time and event for value, event in observations)
        censored = sum(value == time and not event for value, event in observations)
        if events:
            survival *= 1.0 - events / at_risk
        points.append({
            "time": time, "survival_probability": survival, "at_risk": at_risk,
            "events": events, "censored": censored,
        })
        if median_time is None and survival <= 0.5:
            median_time = time
        at_risk -= events + censored
        last_time = time
    return points, rmst + survival * (horizon - last_time), median_time


def build_group_statistics(
    summaries: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in summaries:
        key = (
            str(row["experiment_design"]), str(row["method"]),
            str(row["evaluation_policy"]),
        )
        groups.setdefault(key, []).append(row)
    result_rows, survival_rows = [], []
    for (design, method, policy), rows in sorted(groups.items()):
        candidate_horizon = max(int(row["candidate_cap"]) for row in rows)
        ac_horizon = max(
            int(row["expensive_ac_budget"] or 2 * row["candidate_cap"])
            for row in rows
        )
        candidate_obs = [(
            int(
                row["candidate_time_to_first_feasible"]
                if row["event_observed"] else row["candidate_censor_time"]
            ),
            bool(row["event_observed"]),
        ) for row in rows]
        ac_obs = [(
            int(
                row["expensive_ac_time_to_first_feasible"]
                if row["event_observed"] else row["expensive_ac_censor_time"]
            ),
            bool(row["event_observed"]),
        ) for row in rows]
        candidate_points, candidate_rmst, candidate_median = _km(
            candidate_obs, candidate_horizon
        )
        ac_points, ac_rmst, ac_median = _km(ac_obs, ac_horizon)
        common = {
            "experiment_design": design, "method": method,
            "evaluation_policy": policy,
        }
        for axis, points, horizon, rmst, km_median in (
            ("candidate", candidate_points, candidate_horizon,
             candidate_rmst, candidate_median),
            ("expensive_ac", ac_points, ac_horizon, ac_rmst, ac_median),
        ):
            survival_rows.append({
                **common, "time_axis": axis, "time": 0,
                "survival_probability": 1.0, "at_risk": len(rows),
                "events": 0, "censored": 0, "horizon": horizon,
                "rmst": rmst, "km_median_time_to_feasible": km_median,
            })
            survival_rows.extend({
                **common, "time_axis": axis, **point, "horizon": horizon,
                "rmst": rmst, "km_median_time_to_feasible": km_median,
            } for point in points if point["time"] != 0)
        candidates = sum(int(row["candidate_evaluations"]) for row in rows)
        ac_total = sum(int(row["expensive_ac_analysis_count"]) for row in rows)
        nominal = 2 * candidates
        wall_events = [
            float(row["wall_time_to_first_feasible"]) for row in rows
            if row["event_observed"]
        ]
        result_rows.append({
            **common, "runs": len(rows),
            "success_rate": sum(bool(row["event_observed"]) for row in rows) / len(rows),
            "events": sum(bool(row["event_observed"]) for row in rows),
            "censored": sum(not bool(row["event_observed"]) for row in rows),
            "candidate_km_median": candidate_median,
            "candidate_rmst": candidate_rmst,
            "expensive_ac_km_median": ac_median,
            "expensive_ac_rmst": ac_rmst,
            "median_wall_time_to_first_feasible": (
                median(wall_events) if wall_events else None
            ),
            "candidate_evaluations": candidates,
            "expensive_ac_analysis_count": ac_total,
            "ac_analyses_avoided_vs_full_nominal": nominal - ac_total,
            "percent_ac_saved_vs_full_nominal": (
                100.0 * (nominal - ac_total) / nominal if nominal else 0.0
            ),
            "op_rejected_candidates": sum(
                int(row["op_rejected_candidates"]) for row in rows
            ),
            "full_evaluated_candidates": sum(
                int(row["full_evaluated_candidates"]) for row in rows
            ),
            "physics_invalid_candidates": sum(
                int(row["physics_invalid_candidates"]) for row in rows
            ),
            "feasible_candidates": sum(int(row["feasible_candidates"]) for row in rows),
            "ngspice_process_calls": sum(
                int(row["ngspice_process_calls"]) for row in rows
            ),
            "physical_analysis_calls": sum(
                int(row["physical_analysis_calls"]) for row in rows
            ),
            "total_runtime": sum(float(row["total_runtime"]) for row in rows),
        })
    return result_rows, survival_rows


def _bootstrap(
    differences: list[float], rng: np.random.Generator
) -> tuple[float, float]:
    values = np.asarray(differences, dtype=float)
    indices = rng.integers(0, len(values), size=(10_000, len(values)))
    return tuple(float(value) for value in np.percentile(
        values[indices].mean(axis=1), [2.5, 97.5]
    ))


def build_paired_effects(
    summaries: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows, output = list(summaries), []
    rng = np.random.default_rng(62006)
    directions = {
        "ac_analyses_saved": "full_minus_screened_positive_favors_screened",
        "percent_ac_saved": "full_minus_screened_positive_favors_screened",
        "candidate_restricted_time_to_feasible":
            "screened_minus_full_negative_favors_screened",
        "expensive_ac_restricted_time_to_feasible":
            "screened_minus_full_negative_favors_screened",
        "terminal_wall_runtime":
            "screened_minus_full_negative_favors_screened",
    }
    for design in sorted({str(row["experiment_design"]) for row in rows}):
        pooled: dict[str, list[float]] = {}
        for method in sorted({str(row["method"]) for row in rows}):
            selected = [
                row for row in rows
                if row["experiment_design"] == design and row["method"] == method
            ]
            cells = {
                (str(row["evaluation_policy"]), int(row["seed"])): row
                for row in selected
            }
            seeds = sorted({
                int(row["seed"]) for row in selected
                if (FULL_POLICY, int(row["seed"])) in cells
                and (SCREENED_POLICY, int(row["seed"])) in cells
            })
            outcomes = {
                "ac_analyses_saved": [
                    float(cells[(FULL_POLICY, seed)]["expensive_ac_analysis_count"])
                    - float(cells[(SCREENED_POLICY, seed)]["expensive_ac_analysis_count"])
                    for seed in seeds
                ],
                "percent_ac_saved": [
                    100.0 * (
                        float(cells[(FULL_POLICY, seed)]["expensive_ac_analysis_count"])
                        - float(cells[(SCREENED_POLICY, seed)]["expensive_ac_analysis_count"])
                    ) / float(cells[(FULL_POLICY, seed)]["expensive_ac_analysis_count"])
                    for seed in seeds
                ],
                "candidate_restricted_time_to_feasible": [
                    float(
                        cells[(SCREENED_POLICY, seed)]["candidate_time_to_first_feasible"]
                        or cells[(SCREENED_POLICY, seed)]["candidate_cap"]
                    ) - float(
                        cells[(FULL_POLICY, seed)]["candidate_time_to_first_feasible"]
                        or cells[(FULL_POLICY, seed)]["candidate_cap"]
                    ) for seed in seeds
                ],
                "expensive_ac_restricted_time_to_feasible": [
                    float(
                        cells[(SCREENED_POLICY, seed)]["expensive_ac_time_to_first_feasible"]
                        or 200
                    ) - float(
                        cells[(FULL_POLICY, seed)]["expensive_ac_time_to_first_feasible"]
                        or 200
                    ) for seed in seeds
                ],
                "terminal_wall_runtime": [
                    float(cells[(SCREENED_POLICY, seed)]["total_runtime"])
                    - float(cells[(FULL_POLICY, seed)]["total_runtime"])
                    for seed in seeds
                ],
            }
            for outcome, differences in outcomes.items():
                if not differences:
                    continue
                low, high = _bootstrap(differences, rng)
                output.append({
                    "experiment_design": design, "method": method,
                    "outcome": outcome, "direction": directions[outcome],
                    "pairs": len(differences), "mean_difference": fmean(differences),
                    "median_difference": median(differences), "ci95_low": low,
                    "ci95_high": high,
                    "paired_differences": json.dumps(differences),
                })
                pooled.setdefault(outcome, []).extend(differences)
        for outcome, differences in pooled.items():
            low, high = _bootstrap(differences, rng)
            output.append({
                "experiment_design": design, "method": "pooled_descriptive",
                "outcome": outcome, "direction": directions[outcome],
                "pairs": len(differences), "mean_difference": fmean(differences),
                "median_difference": median(differences), "ci95_low": low,
                "ci95_high": high,
                "paired_differences": json.dumps(differences),
            })
    return output


def _bootstrap_median(
    values: list[float], rng: np.random.Generator
) -> tuple[float, float]:
    array = np.asarray(values, dtype=float)
    indices = rng.integers(0, len(array), size=(10_000, len(array)))
    return tuple(float(value) for value in np.percentile(
        np.median(array[indices], axis=1), [2.5, 97.5]
    ))


def _rank(values: list[float]) -> np.ndarray:
    """Return deterministic average ranks for the small H3 method table."""
    array = np.asarray(values, dtype=float)
    order = np.argsort(array, kind="mergesort")
    ranks = np.empty(len(array), dtype=float)
    start = 0
    while start < len(order):
        stop = start + 1
        while stop < len(order) and array[order[stop]] == array[order[start]]:
            stop += 1
        ranks[order[start:stop]] = (start + 1 + stop) / 2.0
        start = stop
    return ranks


def _spearman(left: list[float], right: list[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    left_rank, right_rank = _rank(left), _rank(right)
    if np.std(left_rank) == 0.0 or np.std(right_rank) == 0.0:
        return None
    return float(np.corrcoef(left_rank, right_rank)[0, 1])


def build_hypothesis_decisions(
    summaries: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Apply only the frozen H1-H3 decision rules to accepted formal rows."""
    rows = list(summaries)
    output: dict[str, Any] = {
        "schema_version": 1,
        "decision_rules": "RESEARCH_HYPOTHESES.md",
    }
    formal_a = [
        row for row in rows
        if row["experiment_design"] == "formal_equal_candidate"
    ]
    if formal_a:
        cells = {
            (str(row["method"]), str(row["evaluation_policy"]), int(row["seed"])):
            row for row in formal_a
        }
        paired_percentages: list[float] = []
        method_rows = []
        for method in sorted({str(row["method"]) for row in formal_a}):
            percentages = []
            screened = [
                row for row in formal_a
                if row["method"] == method
                and row["evaluation_policy"] == SCREENED_POLICY
            ]
            for seed in sorted(int(row["seed"]) for row in screened):
                full_ac = float(cells[(method, FULL_POLICY, seed)][
                    "expensive_ac_analysis_count"
                ])
                screened_ac = float(cells[(method, SCREENED_POLICY, seed)][
                    "expensive_ac_analysis_count"
                ])
                percentages.append(100.0 * (full_ac - screened_ac) / full_ac)
            paired_percentages.extend(percentages)
            candidates = sum(int(row["candidate_evaluations"]) for row in screened)
            rejection_rate = (
                sum(int(row["op_rejected_candidates"]) for row in screened)
                / candidates
            )
            method_rows.append({
                "method": method,
                "op_rejection_rate": rejection_rate,
                "median_percent_ac_saved": median(percentages),
                "paired_percent_ac_saved": percentages,
            })
        low, high = _bootstrap_median(
            paired_percentages, np.random.default_rng(62006)
        )
        pooled_median = median(paired_percentages)
        output["H1"] = {
            "decision": (
                "supported" if pooled_median > 0.0 and low > 0.0
                else "unsupported"
            ),
            "pooled_paired_median_percent_ac_saved": pooled_median,
            "paired_bootstrap_median_ci95": [low, high],
            "pairs": len(paired_percentages),
        }
        benefits = [float(row["median_percent_ac_saved"]) for row in method_rows]
        rejection_rates = [float(row["op_rejection_rate"]) for row in method_rows]
        benefit_range = max(benefits) - min(benefits)
        rho = _spearman(rejection_rates, benefits)
        output["H3"] = {
            "decision": (
                "supported" if benefit_range >= 10.0
                and rho is not None and rho > 0.5 else "unsupported"
            ),
            "method_results": method_rows,
            "range_method_median_percent_ac_saved": benefit_range,
            "spearman_op_rejection_vs_percent_saved": rho,
        }

    formal_b = [
        row for row in rows if row["experiment_design"] == "formal_equal_cost"
    ]
    if formal_b:
        policy_results = {}
        for policy in (FULL_POLICY, SCREENED_POLICY):
            selected = [
                row for row in formal_b if row["evaluation_policy"] == policy
            ]
            observations = [(
                int(
                    row["expensive_ac_time_to_first_feasible"]
                    if row["event_observed"] else row["expensive_ac_censor_time"]
                ),
                bool(row["event_observed"]),
            ) for row in selected]
            _, rmst, km_median = _km(observations, 200)
            policy_results[policy] = {
                "runs": len(selected),
                "events": sum(bool(row["event_observed"]) for row in selected),
                "success_rate": (
                    sum(bool(row["event_observed"]) for row in selected)
                    / len(selected)
                ),
                "pooled_expensive_ac_rmst": rmst,
                "pooled_expensive_ac_km_median": km_median,
            }
        full = policy_results[FULL_POLICY]
        screened = policy_results[SCREENED_POLICY]
        lower_rmst = (
            screened["pooled_expensive_ac_rmst"]
            < full["pooled_expensive_ac_rmst"]
        )
        no_lower_success = screened["success_rate"] >= full["success_rate"]
        improvements = int(lower_rmst) + int(no_lower_success)
        output["H2"] = {
            "decision": (
                "fully_supported" if improvements == 2
                else "partially_supported" if improvements == 1
                else "unsupported"
            ),
            "screened_lower_pooled_expensive_ac_rmst": lower_rmst,
            "screened_no_lower_success_rate": no_lower_success,
            "policy_results": policy_results,
        }
    return output


def build_violation_tables(
    run_directories: Iterable[str | Path],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_rows = [
        row for directory in run_directories
        for row in load_task6_evaluations(directory)
    ]
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    iterations: dict[tuple[str, str, str, int], list[dict[str, Any]]] = {}
    for row in all_rows:
        key = (
            str(row["experiment_design"]), str(row["method"]),
            str(row["evaluation_policy"]),
        )
        groups.setdefault(key, []).append(row)
        iterations.setdefault((*key, int(row["iteration"])), []).append(row)
    distributions = []
    for (design, method, policy), rows in sorted(groups.items()):
        counts = Counter(
            violation for row in rows
            for violation in row["physics_violation_types"]
        )
        invalid = sum(row["physics_status"] == "invalid" for row in rows)
        for violation, count in sorted(counts.items()):
            distributions.append({
                "experiment_design": design, "method": method,
                "evaluation_policy": policy, "violation_type": violation,
                "count": count, "candidate_count": len(rows),
                "invalid_candidate_count": invalid,
                "candidate_rate": count / len(rows),
                "invalid_conditional_rate": count / invalid if invalid else None,
            })
    iteration_rows = []
    for (design, method, policy, iteration), rows in sorted(iterations.items()):
        violations = [
            float(row["op_constraint_violation"]) for row in rows
            if row["op_constraint_violation"] is not None
        ]
        invalid = sum(row["physics_status"] == "invalid" for row in rows)
        iteration_rows.append({
            "experiment_design": design, "method": method,
            "evaluation_policy": policy, "iteration": iteration,
            "candidate_count": len(rows), "invalid_count": invalid,
            "invalid_rate": invalid / len(rows),
            "mean_violation_count": fmean(
                int(row["physics_violation_count"]) for row in rows
            ),
            "mean_op_constraint_violation": (
                fmean(violations) if violations else None
            ),
        })
    return distributions, iteration_rows


def _plot_statistics(
    survival: list[dict[str, Any]],
    violations: list[dict[str, Any]],
    output: Path,
) -> None:
    import matplotlib.pyplot as plt

    plot_directory = output / "plots"
    plot_directory.mkdir(parents=True, exist_ok=True)
    designs = sorted({str(row["experiment_design"]) for row in survival})
    for design in designs:
        for axis in ("candidate", "expensive_ac"):
            chosen = [
                row for row in survival
                if row["experiment_design"] == design and row["time_axis"] == axis
            ]
            figure, panels = plt.subplots(
                2, 2, figsize=(11, 8), constrained_layout=True
            )
            try:
                for method, panel in zip(
                    sorted({row["method"] for row in chosen}), panels.flat
                ):
                    for policy, color in (
                        (FULL_POLICY, "#1f77b4"),
                        (SCREENED_POLICY, "#d62728"),
                    ):
                        curve = sorted(
                            (
                                row for row in chosen
                                if row["method"] == method
                                and row["evaluation_policy"] == policy
                            ),
                            key=lambda row: int(row["time"]),
                        )
                        if curve:
                            panel.step(
                                [row["time"] for row in curve],
                                [row["survival_probability"] for row in curve],
                                where="post", label=policy, color=color,
                            )
                    panel.set_title(method)
                    panel.set_ylim(-0.02, 1.02)
                    panel.grid(True, linestyle=":", alpha=0.5)
                    panel.legend()
                figure.supxlabel(
                    "Candidate evaluations" if axis == "candidate"
                    else "Logical differential + common-mode AC analyses"
                )
                figure.supylabel("Probability no feasible design yet")
                figure.suptitle(f"Task 6 {design}: {axis} time to feasible")
                figure.savefig(
                    plot_directory / f"{design}_{axis}_survival.png", dpi=160
                )
            finally:
                plt.close(figure)

        chosen = [
            row for row in violations if row["experiment_design"] == design
        ]
        figure, panels = plt.subplots(
            2, 2, figsize=(11, 8), constrained_layout=True
        )
        try:
            for method, panel in zip(
                sorted({row["method"] for row in chosen}), panels.flat
            ):
                for policy, color in (
                    (FULL_POLICY, "#1f77b4"),
                    (SCREENED_POLICY, "#d62728"),
                ):
                    curve = sorted(
                        (
                            row for row in chosen
                            if row["method"] == method
                            and row["evaluation_policy"] == policy
                        ),
                        key=lambda row: int(row["iteration"]),
                    )
                    if curve:
                        panel.plot(
                            [row["iteration"] for row in curve],
                            [row["invalid_rate"] for row in curve],
                            label=policy, color=color,
                        )
                panel.set_title(method)
                panel.set_ylim(-0.02, 1.02)
                panel.grid(True, linestyle=":", alpha=0.5)
                panel.legend()
            figure.supxlabel("Candidate iteration")
            figure.supylabel("Physics-invalid fraction across seeds")
            figure.suptitle(f"Task 6 {design}: violation trajectory")
            figure.savefig(
                plot_directory / f"{design}_physics_invalid_rate.png", dpi=160
            )
        finally:
            plt.close(figure)


def write_task6_statistics(
    summaries: Iterable[dict[str, Any]], output_directory: str | Path
) -> dict[str, Path]:
    rows, output = list(summaries), Path(output_directory).resolve()
    groups, survival = build_group_statistics(rows)
    paired = build_paired_effects(
        row for row in rows if row["experiment_design"] != "smoke"
    )
    distributions, iterations = build_violation_tables(
        str(row["output_directory"]) for row in rows
    )
    paths = {
        "run_results": write_table(output / "run_results.csv", RUN_COLUMNS, rows),
        "group_summary": write_table(
            output / "group_summary.csv", GROUP_COLUMNS, groups
        ),
        "survival": write_table(
            output / "survival.csv", SURVIVAL_COLUMNS, survival
        ),
        "paired_effects": write_table(
            output / "paired_effects.csv", PAIRED_COLUMNS, paired
        ),
        "violation_distribution": write_table(
            output / "violation_distribution.csv",
            VIOLATION_COLUMNS, distributions,
        ),
        "violation_by_iteration": write_table(
            output / "violation_by_iteration.csv",
            VIOLATION_ITERATION_COLUMNS, iterations,
        ),
    }
    decisions_path = output / "hypothesis_decisions.json"
    decisions_path.write_text(
        json.dumps(
            build_hypothesis_decisions(rows), indent=2, sort_keys=True,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )
    paths["hypothesis_decisions"] = decisions_path
    _plot_statistics(survival, iterations, output)
    return paths
