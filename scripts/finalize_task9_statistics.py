"""Generate the pre-registered Task 9 statistical result package."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path
import random
from statistics import fmean, median
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from circuitpilot.experiments.task8_statistics import kaplan_meier, paired_effect  # noqa: E402
from circuitpilot.task9_protocol import (  # noqa: E402
    NOMINAL_FIRST_ORDER,
    STATIC_WORST_FIRST_ORDER,
)


TASK9 = ROOT / "research" / "sky130" / "two_stage_ota" / "task9"
RESULTS = TASK9 / "results"
STATISTICS = RESULTS / "statistics"
DESIGNS = ("smoke", "equal_candidate", "equal_simulation_time")
FORMAL_DESIGNS = ("equal_candidate", "equal_simulation_time")
METHODS = ("random", "de", "tpe", "bo")
POLICIES = ("full", "hierarchical")
BOOTSTRAP_SEED = 92_009
BOOTSTRAP_RESAMPLES = 10_000
AXES = {
    "candidate_count": ("candidate_time_to_first_feasible", "candidate_count"),
    "corner_evaluations_started": ("corner_time_to_first_feasible", "corners_started"),
    "op_calls": ("op_time_to_first_feasible", "op_calls"),
    "ac_calls": ("ac_time_to_first_feasible", "ac_calls"),
    "transient_calls": ("transient_time_to_first_feasible", "transient_calls"),
    "accumulated_ngspice_seconds": (
        "ngspice_time_to_first_feasible",
        "accumulated_ngspice_seconds",
    ),
}
WORST_FIELDS = {
    "gain": "worst_corner_for_gain",
    "ugf": "worst_corner_for_ugf",
    "phase_margin": "worst_corner_for_phase_margin",
    "power": "worst_corner_for_power",
    "positive_slew": "worst_corner_for_slew_positive",
    "negative_slew": "worst_corner_for_slew_negative",
    "output_margin": "worst_corner_for_output_margin",
}
CONSTRAINT_TAXONOMY = {
    "operating_region": "operating_region_failure",
    "gain_min": "gain_failure",
    "ugf_min": "ugf_failure",
    "phase_margin_min": "phase_margin_failure",
    "power_max": "power_failure",
    "positive_slew_min": "positive_slew_failure",
    "negative_slew_min": "negative_slew_failure",
    "output_low": "output_bias_failure",
    "output_high": "output_bias_failure",
}


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_csv(path: Path, fieldnames: Iterable[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fieldnames))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def _truth(value: Any) -> bool:
    return value is True or str(value).casefold() == "true"


def _evaluation_path(design: str) -> Path:
    plain = RESULTS / design / "evaluations.csv"
    compressed = RESULTS / design / "evaluations.csv.gz"
    if plain.is_file():
        return plain
    if compressed.is_file():
        return compressed
    raise FileNotFoundError(f"missing Task 9 evaluations for {design}")


def _iter_evaluations(design: str):
    path = _evaluation_path(design)
    csv.field_size_limit(1_000_000_000)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", newline="") as handle:
        yield from csv.DictReader(handle)


def _load_summaries() -> dict[str, list[dict[str, Any]]]:
    result = {}
    for design in DESIGNS:
        state = _json(RESULTS / design / "suite_state.json")
        fairness = _json(RESULTS / design / "fairness_validation.json")
        if state["status"] != "success" or fairness["status"] != "pass":
            raise RuntimeError(f"Task 9 suite is not accepted: {design}")
        rows = _json(RESULTS / design / "cell_summaries.json")
        if len(rows) != (24 if design == "smoke" else 80):
            raise RuntimeError(f"Task 9 suite has wrong cell count: {design}")
        result[design] = rows
    return result


def _observation(row: dict[str, Any], axis: str) -> tuple[float, bool]:
    event_field, terminal_field = AXES[axis]
    event = bool(row["event_observed"])
    value = row[event_field] if event else row[terminal_field]
    if value is None:
        return float(row[terminal_field]), False
    return float(value), event


def _survival(summaries: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    curves: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    for design in FORMAL_DESIGNS:
        for method in (*METHODS, "pooled"):
            selected = summaries[design] if method == "pooled" else [
                row for row in summaries[design] if row["method"] == method
            ]
            for axis in AXES:
                maxima = {
                    policy: max(
                        _observation(row, axis)[0]
                        for row in selected
                        if row["policy"] == policy
                    )
                    for policy in POLICIES
                }
                horizon = min(maxima.values())
                for policy in POLICIES:
                    observations = [
                        _observation(row, axis)
                        for row in selected
                        if row["policy"] == policy
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
                        for point in estimate.points
                        if point.time != 0.0
                    )
    fields = (
        "experiment_design", "method", "policy", "axis", "runs", "events",
        "censored", "horizon", "rmst", "km_median_time_to_feasible",
    )
    _write_csv(STATISTICS / "rmst_summary.csv", fields, groups)
    _write_csv(
        STATISTICS / "kaplan_meier_curves.csv",
        fields + (
            "time", "survival_probability", "at_risk", "point_events",
            "point_censored",
        ),
        curves,
    )
    return groups


def _paired_statistics(summaries: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    definitions = {
        "corners_started_saved": lambda full, hier: float(full["corners_started"]) - float(hier["corners_started"]),
        "op_calls_saved": lambda full, hier: float(full["op_calls"]) - float(hier["op_calls"]),
        "ac_calls_saved": lambda full, hier: float(full["ac_calls"]) - float(hier["ac_calls"]),
        "transient_calls_saved": lambda full, hier: float(full["transient_calls"]) - float(hier["transient_calls"]),
        "process_calls_saved": lambda full, hier: float(full["process_calls"]) - float(hier["process_calls"]),
        "ngspice_seconds_saved": lambda full, hier: float(full["accumulated_ngspice_seconds"]) - float(hier["accumulated_ngspice_seconds"]),
        "ngspice_percent_saved": lambda full, hier: 100.0 * (
            float(full["accumulated_ngspice_seconds"]) - float(hier["accumulated_ngspice_seconds"])
        ) / float(full["accumulated_ngspice_seconds"]),
        "outer_wall_seconds_saved": lambda full, hier: float(full["outer_wall_seconds"]) - float(hier["outer_wall_seconds"]),
        "success_difference_hier_minus_full": lambda full, hier: float(bool(hier["event_observed"])) - float(bool(full["event_observed"])),
        "completed_candidate_throughput_hier_minus_full": lambda full, hier: float(hier.get("completed_candidate_count", hier["candidate_count"])) - float(full.get("completed_candidate_count", full["candidate_count"])),
        "budget_overshoot_full_minus_hier": lambda full, hier: float(full["budget_overshoot_seconds"]) - float(hier["budget_overshoot_seconds"]),
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
                for outcome, operation in definitions.items():
                    value = operation(full, hier)
                    method_values[outcome].append(value)
                    pooled[outcome].append(value)
                    difference_rows.append(
                        {
                            "experiment_design": design,
                            "method": method,
                            "seed": seed,
                            "outcome": outcome,
                            "difference": value,
                        }
                    )
            for outcome, values in method_values.items():
                effects.append(
                    {
                        "experiment_design": design,
                        "method": method,
                        "outcome": outcome,
                        **paired_effect(values, seed=BOOTSTRAP_SEED, resamples=BOOTSTRAP_RESAMPLES),
                    }
                )
        for outcome, values in pooled.items():
            effects.append(
                {
                    "experiment_design": design,
                    "method": "pooled_descriptive",
                    "outcome": outcome,
                    **paired_effect(values, seed=BOOTSTRAP_SEED, resamples=BOOTSTRAP_RESAMPLES),
                }
            )
    _write_csv(
        STATISTICS / "paired_differences.csv",
        ("experiment_design", "method", "seed", "outcome", "difference"),
        difference_rows,
    )
    _write_json(STATISTICS / "paired_effects.json", effects)
    return effects


def _primary_rmst_effects(
    summaries: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    rows = summaries["equal_simulation_time"]
    effects = []
    rng_seed = BOOTSTRAP_SEED
    for method in (*METHODS, "pooled"):
        selected = rows if method == "pooled" else [row for row in rows if row["method"] == method]
        cells = {(row["policy"], row["method"], int(row["seed"])): row for row in selected}
        pair_keys = sorted({(row["method"], int(row["seed"])) for row in selected})
        full = [_observation(cells[("full", name, seed)], "accumulated_ngspice_seconds") for name, seed in pair_keys]
        hier = [_observation(cells[("hierarchical", name, seed)], "accumulated_ngspice_seconds") for name, seed in pair_keys]
        horizon = min(max(time for time, _ in full), max(time for time, _ in hier))
        full_rmst = kaplan_meier(full, horizon=horizon).rmst
        hier_rmst = kaplan_meier(hier, horizon=horizon).rmst
        rng = random.Random(rng_seed)
        count = len(pair_keys)
        bootstrap = []
        for _ in range(BOOTSTRAP_RESAMPLES):
            indices = [rng.randrange(count) for _ in range(count)]
            bootstrap.append(
                kaplan_meier([full[index] for index in indices], horizon=horizon).rmst
                - kaplan_meier([hier[index] for index in indices], horizon=horizon).rmst
            )
        ordered = sorted(bootstrap)

        def percentile(fraction: float) -> float:
            position = (len(ordered) - 1) * fraction
            low = int(position)
            high = min(low + 1, len(ordered) - 1)
            weight = position - low
            return ordered[low] * (1.0 - weight) + ordered[high] * weight

        effects.append(
            {
                "experiment_design": "equal_simulation_time",
                "method": method,
                "axis": "accumulated_ngspice_seconds",
                "pairs": count,
                "events_full": sum(event for _, event in full),
                "events_hierarchical": sum(event for _, event in hier),
                "shared_horizon": horizon,
                "full_rmst": full_rmst,
                "hierarchical_rmst": hier_rmst,
                "full_minus_hierarchical_rmst": full_rmst - hier_rmst,
                "bootstrap_ci95_low": percentile(0.025),
                "bootstrap_ci95_high": percentile(0.975),
                "bootstrap_seed": rng_seed,
                "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
            }
        )
    _write_json(STATISTICS / "primary_rmst_effects.json", effects)
    return effects


def _first_failed_corner(corners: list[dict[str, Any]], order: tuple[str, ...]) -> str:
    indexed = {corner["corner_id"]: corner for corner in corners}
    for corner_id in order:
        corner = indexed[corner_id]
        if corner.get("corner_feasible") is not True or any(corner["analysis_errors"].values()):
            return corner_id
    return "none"


def _descriptive_full_matrices() -> dict[str, Any]:
    worst = Counter()
    first_failures = Counter()
    taxonomy = Counter()
    taxonomy_rows = []
    complete_counts = Counter()
    stage_counts = Counter()
    blocker_counts = Counter()
    analysis_failures = 0
    for design in DESIGNS:
        for row in _iter_evaluations(design):
            stage_counts[(design, row["method"], row["policy"], row["evaluation_stage"])] += 1
            if row["first_failing_constraint"]:
                blocker_counts[(design, row["method"], row["policy"], row["first_failing_constraint"])] += 1
            if row["simulation_status"] == "analysis_failed":
                analysis_failures += 1
            if design not in FORMAL_DESIGNS or row["policy"] != "full":
                continue
            if row["simulation_status"] != "success":
                continue
            corners = json.loads(row["corner_results"])
            if not all(set(corner["completed_analyses"]) == {"op", "ac", "transient"} for corner in corners):
                continue
            complete_counts[design] += 1
            metrics = json.loads(row["worst_metrics"])
            for metric, field in WORST_FIELDS.items():
                worst[(design, metric, metrics.get(field) or "unavailable")] += 1
            for order_name, order in (
                ("nominal_first", NOMINAL_FIRST_ORDER),
                ("static_worst_first", STATIC_WORST_FIRST_ORDER),
            ):
                first_failures[(design, order_name, _first_failed_corner(corners, order))] += 1
            failed = [
                corner
                for corner in corners
                if corner.get("corner_feasible") is not True or any(corner["analysis_errors"].values())
            ]
            labels = set()
            if any(corner["process_corner"] != "tt" for corner in failed):
                labels.add("process_corner_failure")
            if any(float(corner["vdd_v"]) < 1.8 for corner in failed):
                labels.add("low_voltage_failure")
            if any(float(corner["temperature_c"]) > 27.0 for corner in failed):
                labels.add("high_temperature_failure")
            constraint_labels = set()
            for corner in failed:
                for constraint, value in corner["constraint_components"].items():
                    if value is not None and float(value) > 0.0:
                        constraint_labels.add(CONSTRAINT_TAXONOMY[constraint])
            labels.update(constraint_labels)
            if len(constraint_labels) > 1:
                labels.add("multiple_constraint_failure")
            for label in labels:
                taxonomy[(design, label)] += 1
            taxonomy_rows.append(
                {
                    "experiment_design": design,
                    "method": row["method"],
                    "seed": row["seed"],
                    "iteration": row["iteration"],
                    "labels": json.dumps(sorted(labels), separators=(",", ":")),
                }
            )
    worst_rows = [
        {
            "experiment_design": design,
            "metric": metric,
            "corner_id": corner,
            "count": count,
            "complete_full_candidates": complete_counts[design],
            "fraction": count / complete_counts[design],
        }
        for (design, metric, corner), count in sorted(worst.items())
    ]
    first_rows = [
        {
            "experiment_design": design,
            "order": order,
            "corner_id": corner,
            "count": count,
            "complete_full_candidates": complete_counts[design],
            "fraction": count / complete_counts[design],
        }
        for (design, order, corner), count in sorted(first_failures.items())
    ]
    taxonomy_summary = [
        {
            "experiment_design": design,
            "failure_label": label,
            "count": count,
            "complete_full_candidates": complete_counts[design],
            "fraction": count / complete_counts[design],
        }
        for (design, label), count in sorted(taxonomy.items())
    ]
    stage_rows = [
        {
            "experiment_design": design,
            "method": method,
            "policy": policy,
            "evaluation_stage": stage,
            "count": count,
        }
        for (design, method, policy, stage), count in sorted(stage_counts.items())
    ]
    blocker_rows = [
        {
            "experiment_design": design,
            "method": method,
            "policy": policy,
            "first_failing_constraint": blocker,
            "count": count,
        }
        for (design, method, policy, blocker), count in sorted(blocker_counts.items())
    ]
    _write_csv(
        STATISTICS / "worst_corner_distribution.csv",
        ("experiment_design", "metric", "corner_id", "count", "complete_full_candidates", "fraction"),
        worst_rows,
    )
    _write_csv(
        STATISTICS / "first_failing_corner_distribution.csv",
        ("experiment_design", "order", "corner_id", "count", "complete_full_candidates", "fraction"),
        first_rows,
    )
    _write_csv(
        STATISTICS / "failure_taxonomy.csv",
        ("experiment_design", "failure_label", "count", "complete_full_candidates", "fraction"),
        taxonomy_summary,
    )
    _write_csv(
        STATISTICS / "failure_taxonomy_by_candidate.csv",
        ("experiment_design", "method", "seed", "iteration", "labels"),
        taxonomy_rows,
    )
    _write_csv(
        STATISTICS / "stage_distribution.csv",
        ("experiment_design", "method", "policy", "evaluation_stage", "count"),
        stage_rows,
    )
    _write_csv(
        STATISTICS / "first_failing_constraint.csv",
        ("experiment_design", "method", "policy", "first_failing_constraint", "count"),
        blocker_rows,
    )
    return {
        "complete_full_candidates": dict(complete_counts),
        "analysis_failure_count": analysis_failures,
    }


def _effect(effects: list[dict[str, Any]], design: str, outcome: str) -> dict[str, Any]:
    return next(
        row
        for row in effects
        if row["experiment_design"] == design
        and row["method"] == "pooled_descriptive"
        and row["outcome"] == outcome
    )


def _decisions(
    summaries: dict[str, list[dict[str, Any]]],
    effects: list[dict[str, Any]],
    survival: list[dict[str, Any]],
) -> dict[str, Any]:
    replay = _json(TASK9 / "replay" / "replay_summary.json")
    gap = _json(TASK9 / "nominal_gap" / "nominal_gap_summary.json")
    shadow_rows = [row for row in summaries["smoke"] if row["policy"] == "hierarchical"]
    shadow_false = sum(int(row["shadow_false_rejection_count"]) for row in shadow_rows)
    shadow_count = sum(int(row["shadow_audit_candidates"]) for row in shadow_rows)
    replay_summaries = replay["summaries"]
    h1 = all(
        int(item["false_pvt_acceptance_count"]) == 0
        and int(item["false_pvt_rejection_count"]) == 0
        for item in replay_summaries.values()
    ) and shadow_false == 0
    h2_effects = {
        name: _effect(effects, "equal_candidate", name)
        for name in (
            "corners_started_saved", "op_calls_saved", "ac_calls_saved",
            "transient_calls_saved", "process_calls_saved",
        )
    }
    required_h2 = (
        "corners_started_saved", "ac_calls_saved", "transient_calls_saved",
        "process_calls_saved",
    )
    h2 = all(
        h2_effects[name]["median_difference"] > 0.0
        and h2_effects[name]["ci95_low"] > 0.0
        for name in required_h2
    )
    seconds = _effect(effects, "equal_candidate", "ngspice_seconds_saved")
    percent = _effect(effects, "equal_candidate", "ngspice_percent_saved")
    h3 = seconds["ci95_low"] > 0.0 and percent["median_difference"] >= 20.0
    equal_time = summaries["equal_simulation_time"]
    success = {
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
    h4 = success["hierarchical"] > success["full"] and rmst["hierarchical"] < rmst["full"]
    h5 = int(gap["nominal_feasible_but_pvt_failed_count"]) > 0
    decisions = {
        "H1": {
            "supported": h1,
            "replay": replay_summaries,
            "smoke_shadow_candidates": shadow_count,
            "smoke_shadow_false_rejections": shadow_false,
        },
        "H2": {"supported": h2, "effects": h2_effects},
        "H3": {"supported": h3, "seconds": seconds, "percent": percent},
        "H4": {
            "supported": h4,
            "successes_out_of_40": success,
            "success_rates": {name: value / 40.0 for name, value in success.items()},
            "pooled_ngspice_rmst": rmst,
        },
        "H5": {
            "supported": h5,
            "nominal_feasible": int(gap["nominal_feasible_unique_design_count"]),
            "nominal_feasible_but_pvt_failed": int(gap["nominal_feasible_but_pvt_failed_count"]),
        },
    }
    _write_json(STATISTICS / "hypothesis_decisions.json", decisions)
    return decisions


def _totals(rows: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    selected = [row for row in rows if row["policy"] == policy]
    numeric = (
        "candidate_count", "completed_candidate_count", "budget_terminal_candidate_count",
        "corners_started", "corners_completed", "op_calls", "ac_calls",
        "transient_calls", "process_calls", "accumulated_ngspice_seconds",
        "outer_wall_seconds", "orchestration_seconds", "feasible_candidates",
    )
    result = {}
    for name in numeric:
        result[name] = sum(float(row.get(name, row["candidate_count"] if name == "completed_candidate_count" else 0)) for row in selected)
    for name in numeric[:9] + ("feasible_candidates",):
        result[name] = int(result[name])
    result["successful_runs"] = sum(bool(row["event_observed"]) for row in selected)
    result["run_count"] = len(selected)
    result["maximum_budget_overshoot_seconds"] = max(float(row["budget_overshoot_seconds"]) for row in selected)
    return result


def _file_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_hash_manifest() -> None:
    """Hash every retained Task 9 artifact, excluding local checkpoint runs."""

    manifest_path = TASK9 / "file_hashes.json"
    files = []
    for path in sorted(TASK9.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path == manifest_path:
            continue
        relative = path.relative_to(TASK9)
        if "runs" in relative.parts:
            continue
        files.append(
            {
                "path": relative.as_posix(),
                "bytes": path.stat().st_size,
                "sha256": _file_hash(path),
            }
        )
    _write_json(
        manifest_path,
        {
            "schema_version": "task9_file_hashes_v1",
            "file_count": len(files),
            "files": files,
        },
    )


def main() -> None:
    summaries = _load_summaries()
    STATISTICS.mkdir(parents=True, exist_ok=True)
    effects = _paired_statistics(summaries)
    survival = _survival(summaries)
    primary = _primary_rmst_effects(summaries)
    descriptive = _descriptive_full_matrices()
    decisions = _decisions(summaries, effects, survival)
    totals = {
        design: {policy: _totals(summaries[design], policy) for policy in POLICIES}
        for design in DESIGNS
    }
    protocol = _json(TASK9 / "task9_protocol_manifest.json")
    summary = {
        "schema_version": "task9_final_statistics_v1",
        "status": "complete",
        "task9_protocol_hash": protocol["hashes"]["task9_protocol_hash"],
        "pvt_benchmark_hash": protocol["hashes"]["pvt_benchmark_hash"],
        "bootstrap_seed": BOOTSTRAP_SEED,
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "totals": totals,
        "primary_rmst_effects": primary,
        "hypothesis_decisions": {
            name: item["supported"] for name, item in decisions.items()
        },
        "descriptive": descriptive,
        "formal_evidence": {
            design: {
                "path": _evaluation_path(design).relative_to(ROOT).as_posix(),
                "sha256": _file_hash(_evaluation_path(design)),
            }
            for design in FORMAL_DESIGNS
        },
    }
    _write_json(RESULTS / "task9_summary.json", summary)
    _write_hash_manifest()
    print(RESULTS / "task9_summary.json")


if __name__ == "__main__":
    main()
