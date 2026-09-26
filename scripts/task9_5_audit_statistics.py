"""Recalculate Task 6--9 RMST using a common observed support horizon.

This script reads historical evidence and writes only Task 9.5 addenda.
"""

from __future__ import annotations

from collections import defaultdict
import csv
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from circuitpilot.experiments.task9_5_statistics import (  # noqa: E402
    common_supported_horizon, supported_km,
)


BASE = ROOT / "research/sky130/two_stage_ota"
OUTPUT = BASE / "task9_5/statistics"
T6 = ROOT / "research/sky130/differential_amplifier/task6/results"
METHODS = ("random", "de", "tpe", "bo")


def csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def json_rows(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def truth(value: Any) -> bool:
    return value is True or str(value).lower() == "true"


def number(value: Any) -> float:
    return float(value)


def put(
    store: dict[tuple[str, str, str, str], list[tuple[float, bool]]],
    task: str, design: str, method: str, policy: str, axis: str,
    observation: tuple[float, bool],
) -> None:
    store[(task, design, method, policy, axis)].append(observation)
    put_pooled_key = (task, design, "pooled", policy, axis)
    store[put_pooled_key].append(observation)


def task6(store: dict) -> None:
    for design in ("smoke", "formal_equal_candidate", "formal_equal_cost"):
        source = T6 / design / "statistics"
        for row in csv_rows(source / "run_results.csv"):
            method, policy = row["method"], row["evaluation_policy"]
            event = truth(row["event_observed"])
            fields = {
                "candidate_count": ("candidate_time_to_first_feasible", "candidate_censor_time"),
                "expensive_ac_calls": ("expensive_ac_time_to_first_feasible", "expensive_ac_censor_time"),
            }
            for axis, (event_field, censor_field) in fields.items():
                value = row[event_field] if event else row[censor_field]
                put(store, "task6", design, method, policy, axis, (number(value), event))


def task7(store: dict) -> None:
    for design in ("smoke", "formal"):
        path = BASE / "results" / design / "evaluations.csv"
        rows = csv_rows(path)
        by_run = defaultdict(list)
        for row in rows:
            by_run[(row["method"], row["seed"], row["run_id"])].append(row)
        for (method, _, _), candidates in by_run.items():
            candidates.sort(key=lambda row: int(row["iteration"]))
            first = next((row for row in candidates if truth(row["is_feasible"])), None)
            end = first if first is not None else candidates[-1]
            event = first is not None
            axes = {
                "candidate_count": number(end["candidate_evaluations_cumulative"]),
                "op_calls": number(end["op_calls_cumulative"]),
                "ac_calls": number(end["ac_calls_cumulative"]),
                "transient_calls": number(end["transient_calls_cumulative"]),
                "process_calls": number(end["ngspice_process_calls_cumulative"]),
            }
            prefix = candidates[:candidates.index(end) + 1]
            axes["accumulated_analysis_seconds"] = sum(
                number(row[field] or 0)
                for row in prefix
                for field in ("op_runtime_seconds", "ac_runtime_seconds", "transient_runtime_seconds")
            )
            for axis, time in axes.items():
                put(store, "task7", design, method, "full", axis, (time, event))


def task8_or_9(store: dict, task: str) -> None:
    task_path = BASE / ("task8" if task == "task8" else "task9")
    fields = {
        "candidate_count": ("candidate_time_to_first_feasible", "candidate_count"),
        "ac_calls": ("ac_time_to_first_feasible", "ac_calls"),
        "transient_calls": ("transient_time_to_first_feasible", "transient_calls"),
        "accumulated_ngspice_seconds": (
            "ngspice_time_to_first_feasible", "accumulated_ngspice_seconds",
        ),
    }
    if task == "task9":
        fields["op_calls"] = ("op_time_to_first_feasible", "op_calls")
        fields["corners_started"] = ("corner_time_to_first_feasible", "corners_started")
    designs = ("smoke", "equal_candidate", "equal_simulation_time")
    for design in designs:
        path = task_path / "results" / design / "cell_summaries.json"
        for row in json_rows(path):
            event = truth(row["event_observed"])
            for axis, (event_field, terminal_field) in fields.items():
                value = row[event_field] if event else row[terminal_field]
                if value is None:
                    value, event_for_axis = row[terminal_field], False
                else:
                    event_for_axis = event
                put(store, task, design, row["method"], row["policy"], axis,
                    (number(value), event_for_axis))


def old_values() -> dict[tuple[str, str, str, str, str], tuple[float, float]]:
    old = {}
    for design in ("smoke", "formal_equal_candidate", "formal_equal_cost"):
        horizons = {}
        for point in csv_rows(T6 / design / "statistics/survival.csv"):
            axis = "candidate_count" if point["time_axis"] == "candidate" else "expensive_ac_calls"
            horizons[(point["method"], point["evaluation_policy"], axis)] = number(point["horizon"])
        for row in csv_rows(T6 / design / "statistics/group_summary.csv"):
            key = ("task6", design, row["method"], row["evaluation_policy"])
            for axis, field, horizon in (
                ("candidate_count", "candidate_rmst", "candidate_cap"),
                ("expensive_ac_calls", "expensive_ac_rmst", "expensive_ac_budget"),
            ):
                old[(*key, axis)] = (
                    number(row[field]), horizons[(row["method"], row["evaluation_policy"], axis)]
                )
    for design in ("smoke", "formal"):
        source = BASE / "results" / design / "statistics/survival_statistics.json"
        payload = json_rows(source)
        for method, item in payload["methods"].items():
            old[("task7", design, method, "full", "candidate_count")] = (
                number(item["candidate_rmst"]), number(payload["candidate_budget"])
            )
    for task in ("task8", "task9"):
        path = BASE / task / "results/statistics/rmst_summary.csv"
        for row in csv_rows(path):
            old[(task, row["experiment_design"], row["method"], row["policy"], row["axis"])] = (
                number(row["rmst"]), number(row["horizon"])
            )
    return old


def main() -> None:
    store: dict[tuple[str, str, str, str, str], list[tuple[float, bool]]] = defaultdict(list)
    task6(store)
    task7(store)
    task8_or_9(store, "task8")
    task8_or_9(store, "task9")
    historical = old_values()
    comparisons = defaultdict(dict)
    for (task, design, method, policy, axis), observations in store.items():
        comparisons[(task, design, method, axis)][policy] = observations
    output = []
    curves = []
    for (task, design, method, axis), groups in sorted(comparisons.items()):
        horizon = common_supported_horizon(groups)
        for policy, observations in sorted(groups.items()):
            estimate = supported_km(observations, horizon=horizon)
            prior = historical.get((task, design, method, policy, axis))
            output.append({
                "task": task, "design": design, "method": method,
                "policy": policy, "axis": axis, "runs": len(observations),
                "events": sum(event for time, event in observations if time <= horizon),
                "censored_at_horizon": len(observations) - sum(event for time, event in observations if time <= horizon),
                "group_max_observed": max(time for time, _ in observations),
                "common_supported_horizon": horizon, "corrected_rmst": estimate.rmst,
                "corrected_km_median": estimate.median,
                "old_rmst": None if prior is None else prior[0],
                "old_horizon": None if prior is None or prior[1] != prior[1] else prior[1],
                "rmst_change": None if prior is None else estimate.rmst - prior[0],
            })
            curve_common = {
                "task": task, "design": design, "method": method,
                "policy": policy, "axis": axis, "common_supported_horizon": horizon,
            }
            curves.append({**curve_common, "time": 0.0, "survival_probability": 1.0,
                           "at_risk": len(observations), "events": 0, "censored": 0})
            curves.extend(
                {**curve_common, "time": time, "survival_probability": probability,
                 "at_risk": at_risk, "events": events, "censored": censored}
                for time, probability, at_risk, events, censored in estimate.points
                if time != 0.0
            )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    fields = list(output[0])
    with (OUTPUT / "corrected_rmst.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(output)
    with (OUTPUT / "corrected_km_curves.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(curves[0]))
        writer.writeheader()
        writer.writerows(curves)
    summary = {
        "schema_version": "task9_5_supported_rmst_v1",
        "rows": len(output),
        "changed_historical_rows": sum(
            row["rmst_change"] is not None and abs(row["rmst_change"]) > 1e-9
            for row in output
        ),
        "by_task": {
            task: {
                "rows": sum(row["task"] == task for row in output),
                "changed_historical_rows": sum(
                    row["task"] == task and row["rmst_change"] is not None
                    and abs(row["rmst_change"]) > 1e-9 for row in output
                ),
            }
            for task in ("task6", "task7", "task8", "task9")
        },
        "simulator_time_availability": {
            "task6": "not recorded per analysis in frozen evaluation tables; wall time is not substituted",
            "task7": "sum of saved OP, AC, transient runtime columns",
            "task8": "saved accumulated ngspice seconds",
            "task9": "saved accumulated ngspice seconds",
        },
    }
    (OUTPUT / "correction_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
