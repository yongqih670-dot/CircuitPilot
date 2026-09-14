"""Baseline plots sourced only from canonical real-evaluation CSV files."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from circuitpilot.experiments.statistics import load_evaluations
from circuitpilot.experiments.survival import kaplan_meier


def plot_baseline(run_directories: Iterable[str | Path], output_directory: str | Path) -> tuple[Path, ...]:
    """Create protocol plots directly from canonical real-evaluation rows."""
    output = Path(output_directory).resolve()
    output.mkdir(parents=True, exist_ok=True)
    runs = [(Path(path), load_evaluations(path)) for path in run_directories]
    destinations: list[Path] = []

    figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
    for _, rows in runs:
        best = None
        xs, ys = [], []
        for row in rows:
            value = row["objective_value"]
            if value is not None:
                best = float(value) if best is None else min(best, float(value))
            if best is not None:
                xs.append(row["iteration"]); ys.append(best)
        if xs:
            axis.plot(xs, ys, alpha=0.55, label=f"{rows[0]['method']}/seed{rows[0]['seed']}")
    axis.set(xlabel="Simulation evaluations", ylabel="Best objective so far", title="Baseline convergence")
    axis.grid(True, linestyle=":", alpha=0.5); axis.legend(fontsize=7, ncol=2)
    destination = output / "convergence_curve.png"; figure.savefig(destination, dpi=150); plt.close(figure); destinations.append(destination)

    methods: dict[str, list[list[dict]]] = defaultdict(list)
    for _, rows in runs:
        methods[str(rows[0]["method"])].append(rows)
    figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
    for method, method_runs in sorted(methods.items()):
        maximum = max(len(rows) for rows in method_runs)
        budgets = list(range(1, maximum + 1))
        rates = [sum(any(row["is_feasible"] and row["iteration"] <= budget for row in rows) for rows in method_runs) / len(method_runs) for budget in budgets]
        axis.step(budgets, rates, where="post", label=method)
    axis.set(xlabel="Simulation evaluations", ylabel="Run success rate", title="Success rate vs simulation budget", ylim=(-0.02, 1.02))
    axis.grid(True, linestyle=":", alpha=0.5); axis.legend()
    destination = output / "success_rate_vs_budget.png"; figure.savefig(destination, dpi=150); plt.close(figure); destinations.append(destination)

    objective_groups, labels = [], []
    for method, method_runs in sorted(methods.items()):
        values = []
        for rows in method_runs:
            available = [float(row["objective_value"]) for row in rows if row["objective_value"] is not None]
            if available:
                values.append(min(available))
        if values:
            labels.append(method); objective_groups.append(values)
    figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
    if objective_groups:
        axis.boxplot(objective_groups, tick_labels=labels)
    axis.set(xlabel="Method", ylabel="Best objective", title="Best objective distribution (observed runs only)")
    axis.grid(True, axis="y", linestyle=":", alpha=0.5)
    destination = output / "best_objective_distribution.png"; figure.savefig(destination, dpi=150); plt.close(figure); destinations.append(destination)

    first_groups, first_labels = [], []
    for method, method_runs in sorted(methods.items()):
        values = []
        for rows in method_runs:
            first = next((row["iteration"] for row in rows if row["is_feasible"]), None)
            if first is not None:
                values.append(first)
        if values:
            first_labels.append(method); first_groups.append(values)
    figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
    if first_groups:
        axis.boxplot(first_groups, tick_labels=first_labels)
    axis.set(xlabel="Method", ylabel="Simulations to first feasible", title="First-feasible distribution (censored runs omitted)")
    axis.grid(True, axis="y", linestyle=":", alpha=0.5)
    destination = output / "simulations_to_first_feasible.png"; figure.savefig(destination, dpi=150); plt.close(figure); destinations.append(destination)

    figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
    for method, method_runs in sorted(methods.items()):
        horizon = max(len(rows) for rows in method_runs)
        observations = []
        for rows in method_runs:
            first = next((row["iteration"] for row in rows if row["is_feasible"]), None)
            observations.append((first if first is not None else len(rows), first is not None))
        estimate = kaplan_meier(observations, horizon=horizon)
        xs = [0] + [point.time for point in estimate.points]
        ys = [1.0] + [point.survival_probability for point in estimate.points]
        axis.step(xs, ys, where="post", label=f"{method} (RMST={estimate.rmst:.2f})")
    axis.set(
        xlabel="Simulation evaluations",
        ylabel="Probability not yet feasible",
        title="Kaplan-Meier time to first feasible",
        ylim=(-0.02, 1.02),
    )
    axis.grid(True, linestyle=":", alpha=0.5); axis.legend()
    destination = output / "kaplan_meier_time_to_feasible.png"; figure.savefig(destination, dpi=150); plt.close(figure); destinations.append(destination)

    figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
    for _, rows in runs:
        best = None
        xs, ys = [], []
        for row in rows:
            value = row["constraint_violation"]
            if value is not None:
                best = float(value) if best is None else min(best, float(value))
            if best is not None:
                xs.append(row["iteration"]); ys.append(best)
        if xs:
            axis.plot(xs, ys, alpha=0.55, label=f"{rows[0]['method']}/seed{rows[0]['seed']}")
    axis.set(xlabel="Simulation evaluations", ylabel="Best normalized constraint violation", title="Constraint violation vs evaluations")
    axis.grid(True, linestyle=":", alpha=0.5); axis.legend(fontsize=7, ncol=2)
    destination = output / "constraint_violation_vs_evaluations.png"; figure.savefig(destination, dpi=150); plt.close(figure); destinations.append(destination)

    gain_metric = (
        "differential_gain_db"
        if any(
            "differential_gain_db" in row["raw_metrics"]
            for _, rows in runs
            for row in rows
        )
        else "gain_db"
    )
    amplifier_rows = [
        row for _, rows in runs for row in rows
        if row["simulation_status"] == "success"
        and all(
            row["raw_metrics"].get(name) is not None
            for name in (gain_metric, "bandwidth_hz", "dc_power_w")
        )
    ]
    if amplifier_rows:
        for x_metric, y_metric, filename, xlabel, ylabel in (
            ("bandwidth_hz", gain_metric, "gain_vs_bandwidth.png", "Bandwidth (Hz)", "Gain (dB)"),
            ("dc_power_w", gain_metric, "gain_vs_power.png", "DC supply power (W)", "Gain (dB)"),
        ):
            figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
            for feasible, label, marker in ((False, "infeasible", "x"), (True, "feasible", "o")):
                selected = [row for row in amplifier_rows if row["is_feasible"] is feasible]
                if selected:
                    axis.scatter(
                        [row["raw_metrics"][x_metric] for row in selected],
                        [row["raw_metrics"][y_metric] for row in selected],
                        alpha=0.6, marker=marker, label=label,
                    )
            axis.set(xlabel=xlabel, ylabel=ylabel, title=f"{ylabel} vs {xlabel}")
            axis.set_xscale("log")
            axis.grid(True, linestyle=":", alpha=0.5); axis.legend()
            destination = output / filename; figure.savefig(destination, dpi=150); plt.close(figure); destinations.append(destination)

        cmrr_rows = [
            row
            for row in amplifier_rows
            if row["raw_metrics"].get("cmrr_db") is not None
        ]
        if cmrr_rows:
            figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
            for feasible, label, marker in (
                (False, "infeasible", "x"),
                (True, "feasible", "o"),
            ):
                selected = [row for row in cmrr_rows if row["is_feasible"] is feasible]
                if selected:
                    axis.scatter(
                        [row["raw_metrics"][gain_metric] for row in selected],
                        [row["raw_metrics"]["cmrr_db"] for row in selected],
                        alpha=0.6,
                        marker=marker,
                        label=label,
                    )
            axis.set(
                xlabel="Differential gain (dB)",
                ylabel="CMRR (dB)",
                title="CMRR vs differential gain",
            )
            axis.grid(True, linestyle=":", alpha=0.5)
            axis.legend()
            destination = output / "cmrr_vs_gain.png"
            figure.savefig(destination, dpi=150)
            plt.close(figure)
            destinations.append(destination)

        figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
        labels = sorted(methods)
        feasible_counts = [sum(row["is_feasible"] for rows in methods[method] for row in rows) for method in labels]
        infeasible_counts = [sum(not row["is_feasible"] for rows in methods[method] for row in rows) for method in labels]
        axis.bar(labels, infeasible_counts, label="infeasible")
        axis.bar(labels, feasible_counts, bottom=infeasible_counts, label="feasible")
        axis.set(xlabel="Method", ylabel="Candidate count", title="Feasible / infeasible candidate distribution")
        axis.legend(); axis.grid(True, axis="y", linestyle=":", alpha=0.5)
        destination = output / "feasible_infeasible_distribution.png"; figure.savefig(destination, dpi=150); plt.close(figure); destinations.append(destination)
    return tuple(destinations)
