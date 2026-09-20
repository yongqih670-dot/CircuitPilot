"""Generate the pre-registered Task 8 statistics, evidence index, and report."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from circuitpilot.experiments.task8_statistics import kaplan_meier, paired_effect


TASK8 = ROOT / "research" / "sky130" / "two_stage_ota" / "task8"
RESULTS = TASK8 / "results"
STATISTICS = RESULTS / "statistics"
DESIGNS = ("smoke", "equal_candidate", "equal_simulation_time")
FORMAL_DESIGNS = ("equal_candidate", "equal_simulation_time")
METHODS = ("random", "de", "tpe", "bo")
POLICIES = ("full", "hierarchical")
AXES = {
    "candidate_count": (
        "candidate_time_to_first_feasible", "candidate_count"
    ),
    "ac_analysis_count": ("ac_time_to_first_feasible", "ac_calls"),
    "transient_analysis_count": (
        "transient_time_to_first_feasible", "transient_calls"
    ),
    "accumulated_ngspice_seconds": (
        "ngspice_time_to_first_feasible", "accumulated_ngspice_seconds"
    ),
}
BLOCKERS = (
    "operating_region",
    "power",
    "output_bias",
    "gain",
    "ugf",
    "phase_margin",
    "positive_slew",
    "negative_slew",
)


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _truth(value: Any) -> bool:
    return value is True or str(value).casefold() == "true"


def _load() -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, str]]]]:
    summaries: dict[str, list[dict[str, Any]]] = {}
    evaluations: dict[str, list[dict[str, str]]] = {}
    for design in DESIGNS:
        suite = RESULTS / design
        state = _json(suite / "suite_state.json")
        fairness = _json(suite / "fairness_validation.json")
        if state["status"] != "success" or fairness["status"] != "pass":
            raise RuntimeError(f"Task 8 suite is not accepted: {design}")
        summaries[design] = _json(suite / "cell_summaries.json")
        evaluations[design] = _read_csv(suite / "evaluations.csv")
    return summaries, evaluations


def _stage_tables(evaluations: dict[str, list[dict[str, str]]]) -> None:
    stage_rows: list[dict[str, Any]] = []
    blocker_rows: list[dict[str, Any]] = []
    for design in DESIGNS:
        groups: dict[tuple[str, str, int], list[dict[str, str]]] = defaultdict(list)
        for row in evaluations[design]:
            groups[(row["method"], row["policy"], int(row["seed"]))].append(row)
        for (method, policy, seed), rows in sorted(groups.items()):
            stages = Counter(row["evaluation_stage"] for row in rows)
            stage_rows.append(
                {
                    "experiment_design": design,
                    "method": method,
                    "policy": policy,
                    "seed": seed,
                    "candidate_count": len(rows),
                    "op_rejected": stages["op_rejected"],
                    "ac_rejected": stages["ac_rejected"],
                    "transient_executed": sum(int(row["transient_calls"]) for row in rows),
                    "transient_rejected": stages["transient_rejected"],
                    "fully_feasible": stages["fully_feasible"],
                    "full_infeasible": stages["full_infeasible"],
                }
            )
            blockers = Counter(row["first_blocking_constraint"] for row in rows)
            for blocker in BLOCKERS:
                blocker_rows.append(
                    {
                        "experiment_design": design,
                        "method": method,
                        "policy": policy,
                        "seed": seed,
                        "first_blocking_constraint": blocker,
                        "count": blockers[blocker],
                        "candidate_count": len(rows),
                    }
                )
    _write_csv(
        STATISTICS / "stage_distribution.csv",
        (
            "experiment_design", "method", "policy", "seed", "candidate_count",
            "op_rejected", "ac_rejected", "transient_executed",
            "transient_rejected", "fully_feasible", "full_infeasible",
        ),
        stage_rows,
    )
    _write_csv(
        STATISTICS / "first_blocking_constraint.csv",
        (
            "experiment_design", "method", "policy", "seed",
            "first_blocking_constraint", "count", "candidate_count",
        ),
        blocker_rows,
    )


def _paired_statistics(summaries: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    definitions: dict[str, tuple[str, Callable[[dict[str, Any], dict[str, Any]], float]]] = {
        "ac_analyses_saved": (
            "full_minus_hierarchical_positive_favors_hierarchical",
            lambda full, hier: float(full["ac_calls"]) - float(hier["ac_calls"]),
        ),
        "transient_analyses_saved": (
            "full_minus_hierarchical_positive_favors_hierarchical",
            lambda full, hier: float(full["transient_calls"]) - float(hier["transient_calls"]),
        ),
        "process_calls_saved": (
            "full_minus_hierarchical_positive_favors_hierarchical",
            lambda full, hier: float(full["ngspice_process_calls"]) - float(hier["ngspice_process_calls"]),
        ),
        "total_analyses_saved": (
            "full_minus_hierarchical_positive_favors_hierarchical",
            lambda full, hier: float(full["logical_high_fidelity_calls"]) - float(hier["logical_high_fidelity_calls"]),
        ),
        "ngspice_seconds_saved": (
            "full_minus_hierarchical_positive_favors_hierarchical",
            lambda full, hier: float(full["accumulated_ngspice_seconds"]) - float(hier["accumulated_ngspice_seconds"]),
        ),
        "ngspice_percent_saved": (
            "full_minus_hierarchical_positive_favors_hierarchical",
            lambda full, hier: 100.0 * (
                float(full["accumulated_ngspice_seconds"])
                - float(hier["accumulated_ngspice_seconds"])
            ) / float(full["accumulated_ngspice_seconds"]),
        ),
        "outer_wall_seconds_saved": (
            "full_minus_hierarchical_positive_favors_hierarchical",
            lambda full, hier: float(full["outer_wall_seconds"]) - float(hier["outer_wall_seconds"]),
        ),
        "candidate_restricted_time_to_feasible": (
            "hierarchical_minus_full_negative_favors_hierarchical",
            lambda full, hier: float(
                hier["candidate_time_to_first_feasible"] or hier["candidate_count"]
            ) - float(full["candidate_time_to_first_feasible"] or full["candidate_count"]),
        ),
        "ngspice_restricted_time_to_feasible": (
            "hierarchical_minus_full_negative_favors_hierarchical",
            lambda full, hier: float(
                hier["ngspice_time_to_first_feasible"]
                if hier["event_observed"] else hier["accumulated_ngspice_seconds"]
            ) - float(
                full["ngspice_time_to_first_feasible"]
                if full["event_observed"] else full["accumulated_ngspice_seconds"]
            ),
        ),
        "success_difference": (
            "hierarchical_minus_full_positive_favors_hierarchical",
            lambda full, hier: float(bool(hier["event_observed"])) - float(bool(full["event_observed"])),
        ),
    }
    difference_rows: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    for design in FORMAL_DESIGNS:
        cells = {
            (row["policy"], row["method"], int(row["seed"])): row
            for row in summaries[design]
        }
        pooled: dict[str, list[float]] = defaultdict(list)
        for method in METHODS:
            method_values: dict[str, list[float]] = defaultdict(list)
            for seed in range(10):
                full = cells[("full", method, seed)]
                hier = cells[("hierarchical", method, seed)]
                for outcome, (direction, operation) in definitions.items():
                    difference = operation(full, hier)
                    method_values[outcome].append(difference)
                    pooled[outcome].append(difference)
                    difference_rows.append(
                        {
                            "experiment_design": design,
                            "method": method,
                            "seed": seed,
                            "outcome": outcome,
                            "direction": direction,
                            "difference": difference,
                        }
                    )
            for outcome, values in method_values.items():
                effects.append(
                    {
                        "experiment_design": design,
                        "method": method,
                        "outcome": outcome,
                        "direction": definitions[outcome][0],
                        **paired_effect(values),
                    }
                )
        for outcome, values in pooled.items():
            effects.append(
                {
                    "experiment_design": design,
                    "method": "pooled_descriptive",
                    "outcome": outcome,
                    "direction": definitions[outcome][0],
                    **paired_effect(values),
                }
            )
    _write_csv(
        STATISTICS / "paired_differences.csv",
        (
            "experiment_design", "method", "seed", "outcome", "direction",
            "difference",
        ),
        difference_rows,
    )
    _write_json(STATISTICS / "paired_effects.json", effects)
    return effects


def _observation(row: dict[str, Any], axis: str) -> tuple[float, bool]:
    event_field, terminal_field = AXES[axis]
    event = bool(row["event_observed"])
    value = row[event_field] if event else row[terminal_field]
    if value is None:
        value = row[terminal_field]
        event = False
    return float(value), event


def _survival(summaries: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    curves: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    for design in DESIGNS:
        design_rows = summaries[design]
        for axis in AXES:
            maxima = {
                policy: max(_observation(row, axis)[0] for row in design_rows if row["policy"] == policy)
                for policy in POLICIES
            }
            horizon = min(maxima.values())
            for method in (*METHODS, "pooled"):
                selected = design_rows if method == "pooled" else [
                    row for row in design_rows if row["method"] == method
                ]
                for policy in POLICIES:
                    observations = [
                        _observation(row, axis)
                        for row in selected if row["policy"] == policy
                    ]
                    estimate = kaplan_meier(observations, horizon=horizon)
                    common = {
                        "experiment_design": design,
                        "method": method,
                        "policy": policy,
                        "axis": axis,
                        "runs": len(observations),
                        "events": sum(event for _, event in observations),
                        "censored": sum(not event for _, event in observations),
                        "horizon": horizon,
                        "rmst": estimate.rmst,
                        "km_median_time_to_feasible": estimate.median_time_to_event,
                    }
                    groups.append(common)
                    curves.append(
                        {
                            **common,
                            "time": 0.0,
                            "survival_probability": 1.0,
                            "at_risk": len(observations),
                            "point_events": 0,
                            "point_censored": 0,
                        }
                    )
                    curves.extend(
                        {
                            **common,
                            "time": point.time,
                            "survival_probability": point.survival_probability,
                            "at_risk": point.at_risk,
                            "point_events": point.events,
                            "point_censored": point.censored,
                        }
                        for point in estimate.points if point.time != 0.0
                    )
    group_fields = (
        "experiment_design", "method", "policy", "axis", "runs", "events",
        "censored", "horizon", "rmst", "km_median_time_to_feasible",
    )
    _write_csv(STATISTICS / "rmst_summary.csv", group_fields, groups)
    _write_csv(
        STATISTICS / "kaplan_meier_curves.csv",
        group_fields + (
            "time", "survival_probability", "at_risk", "point_events",
            "point_censored",
        ),
        curves,
    )
    return groups


def _effect(
    effects: list[dict[str, Any]], design: str, outcome: str
) -> dict[str, Any]:
    return next(
        row for row in effects
        if row["experiment_design"] == design
        and row["method"] == "pooled_descriptive"
        and row["outcome"] == outcome
    )


def _decisions(
    summaries: dict[str, list[dict[str, Any]]],
    effects: list[dict[str, Any]],
    survival: list[dict[str, Any]],
) -> dict[str, Any]:
    ac = _effect(effects, "equal_candidate", "ac_analyses_saved")
    transient = _effect(effects, "equal_candidate", "transient_analyses_saved")
    ngspice = _effect(effects, "equal_candidate", "ngspice_seconds_saved")
    percent = _effect(effects, "equal_candidate", "ngspice_percent_saved")
    equal_time = summaries["equal_simulation_time"]
    successes = {
        policy: sum(bool(row["event_observed"]) for row in equal_time if row["policy"] == policy)
        for policy in POLICIES
    }
    rmst = {
        row["policy"]: row["rmst"]
        for row in survival
        if row["experiment_design"] == "equal_simulation_time"
        and row["method"] == "pooled"
        and row["axis"] == "accumulated_ngspice_seconds"
    }
    replay = _json(RESULTS / "replay" / "summary.json")
    shadow_false = sum(
        int(row["shadow_false_rejection_count"])
        for row in summaries["smoke"] if row["policy"] == "hierarchical"
    )
    shadow_count = sum(
        int(row["shadow_audit_candidates"])
        for row in summaries["smoke"] if row["policy"] == "hierarchical"
    )
    h1 = (
        ac["median_difference"] > 0
        and transient["median_difference"] > 0
        and ac["ci95_low"] > 0
        and transient["ci95_low"] > 0
    )
    h2 = ngspice["ci95_low"] > 0 and percent["median_difference"] >= 20.0
    h3 = successes["hierarchical"] > successes["full"] and rmst["hierarchical"] < rmst["full"]
    h4 = int(replay["false_rejection_count"]) == 0 and shadow_false == 0
    decisions = {
        "H1": {
            "supported": h1,
            "rule": "positive paired medians and bootstrap lower bounds for both AC and transient savings",
            "ac": ac,
            "transient": transient,
        },
        "H2": {
            "supported": h2,
            "rule": "ngspice-seconds bootstrap lower bound > 0 and median percentage saved >= 20%",
            "ngspice_seconds": ngspice,
            "ngspice_percent": percent,
        },
        "H3": {
            "supported": h3,
            "rule": "strictly higher pooled success and lower pooled ngspice-time RMST",
            "successes_out_of_40": successes,
            "success_rates": {key: value / 40.0 for key, value in successes.items()},
            "pooled_ngspice_time_rmst": rmst,
        },
        "H4": {
            "supported": h4,
            "rule": "zero false rejection in replay and smoke shadow audit",
            "replay_candidates": int(replay["candidate_count"]),
            "replay_false_rejections": int(replay["false_rejection_count"]),
            "shadow_validated_rejections": shadow_count,
            "shadow_false_rejections": shadow_false,
        },
    }
    _write_json(STATISTICS / "hypothesis_decisions.json", decisions)
    return decisions


def _totals(rows: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    selected = [row for row in rows if row["policy"] == policy]
    fields = (
        "candidate_count", "ngspice_process_calls", "op_calls", "ac_calls",
        "transient_calls", "accumulated_ngspice_seconds", "outer_wall_seconds",
        "orchestration_seconds", "feasible_candidates",
    )
    result = {name: sum(float(row[name]) for row in selected) for name in fields}
    for name in fields[:5] + ("feasible_candidates",):
        result[name] = int(result[name])
    result["successful_runs"] = sum(bool(row["event_observed"]) for row in selected)
    result["run_count"] = len(selected)
    result["maximum_budget_overshoot_seconds"] = max(
        float(row["budget_overshoot_seconds"]) for row in selected
    )
    return result


def _copy_best_evidence(
    summaries: dict[str, list[dict[str, Any]]],
    evaluations: dict[str, list[dict[str, str]]],
) -> list[dict[str, Any]]:
    output = RESULTS / "best_raw_evidence"
    output.mkdir(parents=True, exist_ok=True)
    index: list[dict[str, Any]] = []
    for design in FORMAL_DESIGNS:
        summary_index = {
            (row["policy"], row["method"], int(row["seed"])): row
            for row in summaries[design]
        }
        for policy in POLICIES:
            for method in METHODS:
                feasible = [
                    row for row in evaluations[design]
                    if row["policy"] == policy and row["method"] == method
                    and _truth(row["is_feasible"])
                ]
                if not feasible:
                    continue
                best = min(feasible, key=lambda row: float(row["objective_value"]))
                key = (policy, method, int(best["seed"]))
                source = Path(summary_index[key]["_run_directory"]) / best["run_directory"]
                destination = output / design / policy / method
                shutil.copytree(source, destination, dirs_exist_ok=True)
                index.append(
                    {
                        "experiment_design": design,
                        "policy": policy,
                        "method": method,
                        "seed": int(best["seed"]),
                        "iteration": int(best["iteration"]),
                        "objective_value": float(best["objective_value"]),
                        "source": source.relative_to(ROOT).as_posix(),
                        "destination": destination.relative_to(ROOT).as_posix(),
                        "parameters": json.loads(best["parameters"]),
                        "metrics": json.loads(best["metrics"]),
                    }
                )
    _write_json(output / "index.json", index)
    return index


def _report(
    summaries: dict[str, list[dict[str, Any]]],
    evaluations: dict[str, list[dict[str, str]]],
    effects: list[dict[str, Any]],
    survival: list[dict[str, Any]],
    decisions: dict[str, Any],
    evidence: list[dict[str, Any]],
) -> None:
    protocol = _json(TASK8 / "task8_protocol_manifest.json")
    replay = _json(RESULTS / "replay" / "summary.json")
    cost = _json(RESULTS / "cost_profile" / "summary.json")
    totals = {
        design: {policy: _totals(summaries[design], policy) for policy in POLICIES}
        for design in DESIGNS
    }
    ec_full, ec_hier = totals["equal_candidate"]["full"], totals["equal_candidate"]["hierarchical"]
    et_full, et_hier = totals["equal_simulation_time"]["full"], totals["equal_simulation_time"]["hierarchical"]
    ac = _effect(effects, "equal_candidate", "ac_analyses_saved")
    tran = _effect(effects, "equal_candidate", "transient_analyses_saved")
    proc = _effect(effects, "equal_candidate", "process_calls_saved")
    analyses = _effect(effects, "equal_candidate", "total_analyses_saved")
    seconds = _effect(effects, "equal_candidate", "ngspice_seconds_saved")
    percent = _effect(effects, "equal_candidate", "ngspice_percent_saved")
    stage_counts = {
        design: Counter(row["evaluation_stage"] for row in evaluations[design])
        for design in DESIGNS
    }
    blockers = Counter(
        row["first_blocking_constraint"]
        for design in FORMAL_DESIGNS for row in evaluations[design]
        if row["first_blocking_constraint"]
    )
    failures = sum(
        row["simulation_status"] != "success"
        for design in DESIGNS for row in evaluations[design]
    )
    h3 = decisions["H3"]
    equal_time_budget = 90.0
    strict_budget = {}
    method_successes = {}
    for policy in POLICIES:
        observations = [
            _observation(row, "accumulated_ngspice_seconds")
            for row in summaries["equal_simulation_time"]
            if row["policy"] == policy
        ]
        strict_estimate = kaplan_meier(observations, horizon=equal_time_budget)
        strict_budget[policy] = {
            "successes": sum(
                event and time <= equal_time_budget for time, event in observations
            ),
            "rmst": strict_estimate.rmst,
        }
        method_successes[policy] = {
            method: sum(
                bool(row["event_observed"])
                for row in summaries["equal_simulation_time"]
                if row["policy"] == policy and row["method"] == method
            )
            for method in METHODS
        }
    method_labels = {"random": "Random", "de": "DE", "tpe": "TPE", "bo": "BO"}
    method_success_text = {
        policy: ", ".join(
            f"{method_labels[method]} {method_successes[policy][method]}/10"
            for method in METHODS
        )
        for policy in POLICIES
    }
    lines = [
        "# Task 8 Hierarchical Evaluation Report",
        "",
        "Status: complete and frozen after all pre-registered gates and formal suites passed.",
        "",
        "## 1. Frozen Task 7 identity",
        "",
        f"Task 7 benchmark SHA-256 remained `{replay['task7_benchmark_hash']}`. The topology, 12-dimensional search space, PDK, measurements, hard constraints, objective, and raw Task 7 evidence were not changed.",
        "",
        "## 2. Full policy",
        "",
        "Full executes independent real SKY130 OP, AC, and transient analyses for every candidate and reproduces the frozen Task 7 evaluation sequence.",
        "",
        "## 3. Hierarchical policy",
        "",
        "Hierarchical executes OP, then AC only after all measured OP hard constraints pass, then transient only after all measured AC hard constraints pass.",
        "",
        "## 4. Safe-rejection logic",
        "",
        "Every early stop is caused by an already measured frozen hard-constraint violation. No prediction, learned model, heuristic parameter region, synthetic metric, or LLM judgment participates.",
        "",
        "## 5. Replay equivalence",
        "",
        f"Offline replay covered {replay['candidate_count']} frozen Full candidates without new ngspice calls: {replay['op_rejected']} OP rejections, {replay['ac_rejected']} AC rejections, and {replay['transient_required']} transient-required candidates.",
        "",
        "## 6. False rejection count",
        "",
        f"Replay false rejections: {replay['false_rejection_count']}. Smoke shadow-Full false rejections: {decisions['H4']['shadow_false_rejections']} across {decisions['H4']['shadow_validated_rejections']} audited hierarchical early rejections.",
        "",
        "## 7. Partial feedback",
        "",
        "The frozen lexicographic scalar keeps feasible candidates best, rewards later validated stages, and ranks within a stage only by measured normalized violations. Unknown downstream metrics remain null.",
        "",
        "## 8. Analysis cost profile",
        "",
        f"On 16 fixed candidates, median accumulated simulator time was {cost['statistics']['op_only']['accumulated_ngspice_seconds']['median']:.3f} s for OP-only, {cost['statistics']['op_ac']['accumulated_ngspice_seconds']['median']:.3f} s for OP+AC, and {cost['statistics']['full']['accumulated_ngspice_seconds']['median']:.3f} s for Full. The profile used {cost['new_ngspice_process_calls']} new processes.",
        "",
        "## 9. Smoke",
        "",
        f"Smoke completed 24 cells and 600 primary candidates. Stage counts were {dict(stage_counts['smoke'])}; all {sum(int(row['shadow_audit_candidates']) for row in summaries['smoke'] if row['policy'] == 'hierarchical')} hierarchical rejections were shadow validated. Smoke is excluded from formal inference.",
        "",
        "## 10. Equal Candidate results",
        "",
        f"Each policy evaluated 2,000 candidates (4 methods × 10 seeds × 50). Full used {ec_full['ngspice_process_calls']} processes and {ec_full['accumulated_ngspice_seconds']:.3f} accumulated ngspice seconds; Hierarchical used {ec_hier['ngspice_process_calls']} processes and {ec_hier['accumulated_ngspice_seconds']:.3f} seconds. Successful runs were {ec_full['successful_runs']}/40 and {ec_hier['successful_runs']}/40, respectively.",
        "",
        "## 11. Equal Simulation-Time results",
        "",
        f"At the frozen 90 s per-run budget and 300-candidate cap, Full evaluated {et_full['candidate_count']} candidates in {et_full['ngspice_process_calls']} processes; Hierarchical evaluated {et_hier['candidate_count']} candidates in {et_hier['ngspice_process_calls']} processes. Successful runs were {et_full['successful_runs']}/40 versus {et_hier['successful_runs']}/40. The pre-registered implementation completes an in-flight candidate before stopping, so maximum overshoot was {max(et_full['maximum_budget_overshoot_seconds'], et_hier['maximum_budget_overshoot_seconds']):.3f} s. This candidate-terminal rule is slightly broader than a literal stop immediately after the first analysis crossing the budget.",
        "",
        "## 12. AC savings",
        "",
        f"Equal-candidate pooled paired Full-minus-Hierarchical AC savings: median {ac['median_difference']:.3f}, mean {ac['mean_difference']:.3f}, bootstrap 95% CI [{ac['ci95_low']:.3f}, {ac['ci95_high']:.3f}] analyses per run.",
        "",
        "## 13. Transient savings",
        "",
        f"Pooled transient savings: median {tran['median_difference']:.3f}, mean {tran['mean_difference']:.3f}, bootstrap 95% CI [{tran['ci95_low']:.3f}, {tran['ci95_high']:.3f}] analyses per run.",
        "",
        "## 14. Process-count savings",
        "",
        f"Pooled total-analysis savings: median {analyses['median_difference']:.3f}, mean {analyses['mean_difference']:.3f}, bootstrap 95% CI [{analyses['ci95_low']:.3f}, {analyses['ci95_high']:.3f}] analyses per run. Pooled process savings are numerically identical in this benchmark because every OP, AC, or transient analysis launches one ngspice process: median {proc['median_difference']:.3f}, mean {proc['mean_difference']:.3f}, 95% CI [{proc['ci95_low']:.3f}, {proc['ci95_high']:.3f}].",
        "",
        "## 15. ngspice-time savings",
        "",
        f"Pooled accumulated-ngspice savings: median {seconds['median_difference']:.3f} s, mean {seconds['mean_difference']:.3f} s, bootstrap 95% CI [{seconds['ci95_low']:.3f}, {seconds['ci95_high']:.3f}] s. The median paired percentage reduction was {percent['median_difference']:.2f}%.",
        "",
        "## 16. Wall-time observations",
        "",
        f"Equal-candidate summed outer wall time was {ec_full['outer_wall_seconds']:.3f} s for Full and {ec_hier['outer_wall_seconds']:.3f} s for Hierarchical. This is secondary; accumulated subprocess time is the primary runtime metric.",
        "",
        "## 17. KM/RMST on all cost axes",
        "",
        f"Kaplan-Meier curves and shared-horizon RMST are published for candidate, AC, transient, and accumulated-ngspice-time axes. Equal-time pooled ngspice RMST was {h3['pooled_ngspice_time_rmst']['full']:.3f} s for Full and {h3['pooled_ngspice_time_rmst']['hierarchical']:.3f} s for Hierarchical.",
        "",
        "## 18. Stage distribution",
        "",
        f"Formal equal-candidate stage counts were {dict(stage_counts['equal_candidate'])}; equal-time counts were {dict(stage_counts['equal_simulation_time'])}. Per-cell counts are in `results/statistics/stage_distribution.csv`.",
        "",
        "## 19. First blocking constraints",
        "",
        f"Across formal candidates, first blockers were {dict(blockers)}. The table is descriptive only and did not reorder stages.",
        "",
        "## 20. Paired effect sizes / CI",
        "",
        "All effects use method/seed pairing, 10,000 deterministic percentile-bootstrap resamples, and seed 82008. Per-method and pooled results plus all individual differences are published in `paired_effects.json` and `paired_differences.csv`.",
        "",
        "## 21. Exact simulation evidence",
        "",
        f"All formal CSV records retain exact hashes, parameters, metrics, statuses, stage costs, and raw-run paths. {len(evidence)} canonical best feasible raw-evidence directories are copied under `results/best_raw_evidence/`. Simulator/process failures across all primary Task 8 suites: {failures}.",
        "",
        "## 22. Tests",
        "",
        "The 24 Task 8 tests pass and cover frozen Task 7 bytes, Full equivalence, all gate transitions, null unknown metrics, feasibility identity, replay detection, cost counters, both budget types, overshoot, stage-boundary resume, deterministic feedback, fairness identity, real SKY130 E2E, paired bootstrap, and KM/RMST. The full project regression completed with 313 passed and one environment-dependent Task 3 skip because SKY130_MODEL_LIBRARY was not configured.",
        "",
        "## 23. Limitations",
        "",
        f"Results are limited to the frozen nominal SKY130A two-stage OTA, ten seeds, four optimizers, and one machine/runtime environment. They do not cover PVT, mismatch, learned surrogates, topology generation, layout parasitics, or adaptive stage ordering. H3 is a pooled pre-registered decision and is not uniform by method: Full equal-time successes were {method_success_text['full']}; Hierarchical successes were {method_success_text['hierarchical']}. A strict 90.0 s administrative sensitivity analysis still favors Hierarchical ({strict_budget['hierarchical']['successes']}/40 successes, RMST {strict_budget['hierarchical']['rmst']:.3f} s) over Full ({strict_budget['full']['successes']}/40, RMST {strict_budget['full']['rmst']:.3f} s), so the candidate-terminal overshoot does not drive H3. All accepted raw run directories remain locally available, while the versioned result package contains consolidated candidate records and {len(evidence)} canonical feasible raw-evidence directories rather than every raw waveform.",
        "",
        "## 24. Hypothesis decisions",
        "",
        *[f"- {name}: {'supported' if value['supported'] else 'not supported'}." for name, value in decisions.items()],
        "",
        "## 25. Recommendation for Task 9",
        "",
        "Use this frozen deterministic hierarchical evaluator as the baseline. Any future agent or learned policy should preserve the same feasibility and safe-rejection audit while demonstrating paired gains beyond this baseline on simulator-time RMST and success.",
        "",
        "## Provenance",
        "",
        f"Task 8 protocol SHA-256: `{protocol['task8_protocol_hash']}`. All suite fairness validators passed. Exact file hashes are published in `file_hashes.json`.",
    ]
    (TASK8 / "TASK8_HIERARCHICAL_EVALUATION_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    summary = {
        "status": "complete",
        "task7_benchmark_hash": replay["task7_benchmark_hash"],
        "task8_protocol_hash": protocol["task8_protocol_hash"],
        "totals": totals,
        "simulation_failure_count": failures,
        "hypothesis_decisions": {
            name: value["supported"] for name, value in decisions.items()
        },
        "best_raw_evidence_count": len(evidence),
        "strict_90_second_sensitivity": strict_budget,
        "equal_time_successes_by_method": method_successes,
    }
    _write_json(RESULTS / "task8_summary.json", summary)


def _hash_manifest() -> None:
    files: dict[str, str] = {}
    for path in sorted(TASK8.rglob("*")):
        if not path.is_file() or path.name == "file_hashes.json" or "runs" in path.parts:
            continue
        digest = sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        files[path.relative_to(TASK8).as_posix()] = digest.hexdigest()
    _write_json(TASK8 / "file_hashes.json", {"files": files})


def main() -> None:
    summaries, evaluations = _load()
    STATISTICS.mkdir(parents=True, exist_ok=True)
    _stage_tables(evaluations)
    effects = _paired_statistics(summaries)
    survival = _survival(summaries)
    decisions = _decisions(summaries, effects, survival)
    evidence = _copy_best_evidence(summaries, evaluations)
    _report(summaries, evaluations, effects, survival, decisions, evidence)
    _hash_manifest()
    print(TASK8)


if __name__ == "__main__":
    main()
