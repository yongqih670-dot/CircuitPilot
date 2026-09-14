"""Command line entry point for unified CircuitPilot research experiments."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Sequence

from circuitpilot.exceptions import CircuitPilotError
from circuitpilot.experiments.config import (
    ExperimentConfig,
    NgspiceConfig,
    experiment_config_from_mapping,
    load_experiment_config,
)
from circuitpilot.experiments.runner import execute_experiment


def build_parser() -> argparse.ArgumentParser:
    """Build the research experiment CLI parser."""
    parser = argparse.ArgumentParser(
        description="Run a fair, budgeted, reproducible CircuitPilot experiment."
    )
    parser.add_argument("--config", type=Path, help="unified experiment YAML")
    parser.add_argument(
        "--circuit",
        choices=("rc_lowpass", "common_source", "sky130_common_source"),
    )
    parser.add_argument("--method", choices=("random", "de", "tpe", "bo"))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--budget", type=int)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--ngspice", help="ngspice executable name or full path")
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--resume", action="store_true")
    return parser


def _default_config(arguments: argparse.Namespace) -> ExperimentConfig:
    """Build the documented RC random baseline through the same config parser."""
    if arguments.circuit is None or arguments.method is None:
        raise ValueError("--circuit and --method are required without --config")
    if arguments.circuit != "rc_lowpass":
        raise ValueError(
            "transistor benchmarks require --config so model provenance and hashes are explicit"
        )
    return experiment_config_from_mapping(
        {
            "experiment": {
                "name": f"{arguments.circuit}_{arguments.method}_seed{arguments.seed or 0}",
                "circuit": arguments.circuit,
                "method": arguments.method,
                "seed": 0 if arguments.seed is None else arguments.seed,
                "simulation_budget": 50 if arguments.budget is None else arguments.budget,
                "output_dir": str(arguments.output_dir or "research_runs"),
                "resume": arguments.resume,
                "timeout": 60.0 if arguments.timeout is None else arguments.timeout,
            },
            "search_space": {
                "resistance": {
                    "type": "float",
                    "low": 100.0,
                    "high": 10_000.0,
                    "log": True,
                },
                "capacitance": {
                    "type": "float",
                    "low": 1e-9,
                    "high": 1e-6,
                    "log": True,
                },
            },
            "objectives": {
                "bandwidth": {"type": "target", "target": 10_000.0}
            },
            "constraints": {},
            "success_criterion": {
                "metric": "bandwidth",
                "relative_error_threshold": 0.05,
            },
            "optimizer_config": {},
            "ngspice_config": {
                "executable": arguments.ngspice or "ngspice",
                "start_frequency_hz": 10.0,
                "stop_frequency_hz": 10_000_000.0,
                "points_per_decade": 50,
            },
            "pvt_config": {},
        }
    )


def _apply_overrides(
    config: ExperimentConfig, arguments: argparse.Namespace
) -> ExperimentConfig:
    """Apply CLI values by producing another common ExperimentConfig object."""
    ngspice = config.ngspice_config
    if arguments.ngspice is not None:
        ngspice = replace(ngspice, executable=arguments.ngspice)
    return replace(
        config,
        circuit_name=arguments.circuit or config.circuit_name,
        method=arguments.method or config.method,
        seed=config.seed if arguments.seed is None else arguments.seed,
        simulation_budget=(
            config.simulation_budget if arguments.budget is None else arguments.budget
        ),
        output_dir=arguments.output_dir or config.output_dir,
        ngspice_config=ngspice,
        resume=arguments.resume or config.resume,
        timeout=config.timeout if arguments.timeout is None else arguments.timeout,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run one unified experiment and print its method-neutral summary."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        config = (
            load_experiment_config(arguments.config)
            if arguments.config is not None
            else _default_config(arguments)
        )
        config = _apply_overrides(config, arguments)
        result = execute_experiment(config)
    except (CircuitPilotError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    best = result.best_record
    print(f"Run ID: {result.run_id}")
    print(f"Method: {config.method}")
    print(f"Circuit: {config.circuit_name}")
    print(f"Budget: {config.simulation_budget}")
    print(f"Succeeded: {result.budget['evaluations_success']}")
    print(f"Failed: {result.budget['evaluations_failed']}")
    print(f"ngspice calls: {result.budget['ngspice_calls']}")
    print(
        "Best result: "
        + (
            "none"
            if best is None
            else json.dumps(
                {
                    "iteration": best.iteration,
                    "parameters": best.parameters,
                    "metrics": best.raw_metrics,
                    "objective_value": best.objective_value,
                    "constraint_violation": best.constraint_violation,
                },
                sort_keys=True,
                allow_nan=False,
            )
        )
    )
    print(f"Output directory: {result.output_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
