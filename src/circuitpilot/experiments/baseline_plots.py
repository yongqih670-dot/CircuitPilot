"""Baseline plots sourced only from canonical real-evaluation CSV files."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt

from circuitpilot.experiments.statistics import load_evaluations


def plot_baseline(run_directories: Iterable[str | Path], output_directory: str | Path) -> tuple[Path, ...]:
    """Create the four protocol plots without modifying or imputing data."""
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
    return tuple(destinations)
