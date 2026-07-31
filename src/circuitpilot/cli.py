"""Command-line workflow for parameterized CircuitPilot simulations."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from time import monotonic
from typing import Sequence

from circuitpilot.analysis import find_cutoff_frequency, find_highpass_cutoff_frequency
from circuitpilot.circuit_config import (
    ACAnalysisConfig,
    CircuitConfig,
    CircuitType,
    RCHighPassConfig,
    RCLowPassConfig,
    load_circuit_config,
)
from circuitpilot.exceptions import CircuitPilotError
from circuitpilot.experiment_manager import (
    DEFAULT_DATABASE_PATH,
    ExperimentRecord,
    ExperimentRepository,
)
from circuitpilot.netlist_generator import write_netlist
from circuitpilot.parameter_sweep import (
    format_top_solutions,
    plot_sweep_performance,
    rank_solutions,
    run_parameter_sweep,
    save_sweep_results_csv,
)
from circuitpilot.parser import ACAnalysisResult, parse_ac_output
from circuitpilot.plotting import plot_bode
from circuitpilot.simulator import run_ngspice
from circuitpilot.sweep_config import load_sweep_config


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CircuitPilot command-line parser."""
    parser = argparse.ArgumentParser(
        prog="circuitpilot",
        description="Run one ngspice AC analysis or an automated parameter sweep.",
    )
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--config",
        type=Path,
        help="YAML configuration for one circuit simulation",
    )
    input_group.add_argument(
        "--sweep-config",
        type=Path,
        help="YAML target and parameter space for automated optimization",
    )
    parser.add_argument("--resistance", type=float, default=1_000.0, help="R in ohms")
    parser.add_argument(
        "--capacitance", type=float, default=159.154943e-9, help="C in farads"
    )
    parser.add_argument("--start", type=float, default=10.0, help="start frequency in Hz")
    parser.add_argument(
        "--stop", type=float, default=1_000_000.0, help="stop frequency in Hz"
    )
    parser.add_argument(
        "--points", type=int, default=100, help="AC points per decade"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="directory for the netlist, data, log, and plot",
    )
    parser.add_argument(
        "--ngspice", default="ngspice", help="ngspice executable name or full path"
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0, help="simulation timeout in seconds"
    )
    parser.add_argument("--show", action="store_true", help="show the plot interactively")
    parser.add_argument(
        "--experiment-name",
        help="save a successful simulation or sweep to the experiment database",
    )
    parser.add_argument(
        "--experiment-database",
        type=Path,
        default=DEFAULT_DATABASE_PATH,
        help="database used with --experiment-name",
    )

    commands = parser.add_subparsers(dest="command")
    experiment_parser = commands.add_parser(
        "experiment", help="create, list, rank, or compare SQLite experiments"
    )
    experiment_actions = experiment_parser.add_subparsers(
        dest="experiment_command", required=True
    )

    create_parser = experiment_actions.add_parser(
        "create", help="create an experiment from explicit JSON values"
    )
    create_parser.add_argument("--name", required=True)
    create_parser.add_argument(
        "--circuit-type", required=True, choices=[member.value for member in CircuitType]
    )
    create_parser.add_argument(
        "--parameters", required=True, help="JSON object containing circuit parameters"
    )
    create_parser.add_argument("--simulation-time", required=True, type=float)
    create_parser.add_argument(
        "--metrics", required=True, help="JSON object containing numeric metrics"
    )
    create_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)

    list_parser = experiment_actions.add_parser("list", help="list experiment history")
    list_parser.add_argument(
        "--circuit-type", choices=[member.value for member in CircuitType]
    )
    list_parser.add_argument("--limit", type=int)
    list_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)

    best_parser = experiment_actions.add_parser(
        "best", help="show the best experiment for one metric"
    )
    best_parser.add_argument("--metric", required=True)
    best_parser.add_argument(
        "--circuit-type", choices=[member.value for member in CircuitType]
    )
    best_parser.add_argument(
        "--maximize", action="store_true", help="maximize instead of minimize the metric"
    )
    best_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)

    compare_parser = experiment_actions.add_parser(
        "compare", help="compare a metric against the oldest or first selected experiment"
    )
    compare_parser.add_argument("--metric", required=True)
    compare_parser.add_argument("--ids", type=int, nargs="+")
    compare_parser.add_argument(
        "--circuit-type", choices=[member.value for member in CircuitType]
    )
    compare_parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE_PATH)
    return parser


def _legacy_lowpass_config(args: argparse.Namespace) -> CircuitConfig:
    """Convert first-stage command-line flags to the new configuration model."""
    return CircuitConfig(
        circuit=RCLowPassConfig(
            resistance_ohm=args.resistance,
            capacitance_f=args.capacitance,
        ),
        analysis=ACAnalysisConfig(
            start_frequency_hz=args.start,
            stop_frequency_hz=args.stop,
            points_per_decade=args.points,
        ),
    )


def _cutoff_for_config(
    config: CircuitConfig, response: ACAnalysisResult
) -> float | None:
    """Calculate the appropriate cutoff measurement for filter templates."""
    if isinstance(config.circuit, RCLowPassConfig):
        return find_cutoff_frequency(response.frequency_hz, response.gain_db)
    if isinstance(config.circuit, RCHighPassConfig):
        return find_highpass_cutoff_frequency(response.frequency_hz, response.gain_db)
    return None


def _load_json_object(value: str, context: str) -> dict[str, object]:
    """Parse a CLI JSON argument and require an object at its root."""
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CircuitPilotError(f"invalid {context} JSON: {exc}") from exc
    if not isinstance(loaded, dict):
        raise CircuitPilotError(f"{context} JSON must be an object")
    return loaded


def _print_experiment(record: ExperimentRecord) -> None:
    """Print one experiment record without coupling argparse to storage rows."""
    print(f"Experiment ID: {record.experiment_id}")
    print(f"Name: {record.name}")
    print(f"Circuit type: {record.circuit_type}")
    print(f"Simulation time: {record.simulation_time_seconds:.6g} s")
    print(
        "Parameters: "
        + json.dumps(record.parameters, ensure_ascii=False, sort_keys=True)
    )
    print(
        "Metrics: "
        + json.dumps(record.metrics, ensure_ascii=False, sort_keys=True)
    )
    print(f"Created at: {record.created_at}")


def _run_experiment_command(args: argparse.Namespace) -> int:
    """Dispatch SQLite experiment-management subcommands."""
    repository = ExperimentRepository(args.database)
    if args.experiment_command == "create":
        parameters = _load_json_object(args.parameters, "parameters")
        raw_metrics = _load_json_object(args.metrics, "metrics")
        record = repository.create_experiment(
            name=args.name,
            circuit_type=args.circuit_type,
            parameters=parameters,
            simulation_time_seconds=args.simulation_time,
            metrics=raw_metrics,  # type: ignore[arg-type]
        )
        print("Experiment created.")
        _print_experiment(record)
        return 0

    if args.experiment_command == "list":
        records = repository.list_experiments(
            circuit_type=args.circuit_type, limit=args.limit
        )
        print(f"Experiments: {len(records)}")
        print("ID    Created at                 Circuit          Time (s)   Name")
        for record in records:
            print(
                f"{record.experiment_id:<5} {record.created_at:<26} "
                f"{record.circuit_type:<16} "
                f"{record.simulation_time_seconds:<10.6g} {record.name}"
            )
        return 0

    if args.experiment_command == "best":
        record = repository.show_best_result(
            args.metric,
            circuit_type=args.circuit_type,
            minimize=not args.maximize,
        )
        direction = "maximum" if args.maximize else "minimum"
        print(f"Best result by {direction} '{args.metric}'.")
        _print_experiment(record)
        return 0

    comparisons = repository.compare_experiments(
        args.metric,
        experiment_ids=args.ids,
        circuit_type=args.circuit_type,
    )
    print(f"History comparison for metric '{args.metric}'")
    print("ID    Value          Delta          Relative delta   Name")
    for comparison in comparisons:
        relative = (
            "n/a"
            if comparison.relative_difference_from_baseline is None
            else f"{comparison.relative_difference_from_baseline:.6g}"
        )
        print(
            f"{comparison.experiment_id:<5} {comparison.metric_value:<14.6g} "
            f"{comparison.difference_from_baseline:<14.6g} "
            f"{relative:<16} {comparison.experiment_name}"
        )
    return 0


def _save_single_experiment(
    args: argparse.Namespace,
    config: CircuitConfig,
    response: ACAnalysisResult,
    cutoff_hz: float | None,
    simulation_time_seconds: float,
) -> int | None:
    """Optionally persist a completed single simulation and return its id."""
    if args.experiment_name is None:
        return None
    parameters = {
        "circuit": asdict(config.circuit),
        "analysis": asdict(config.analysis),
    }
    metrics: dict[str, float] = {
        "sample_count": float(len(response)),
        "gain_at_start_db": response.gain_db[0],
        "phase_at_start_deg": response.phase_deg[0],
    }
    if cutoff_hz is not None:
        metrics["cutoff_frequency_hz"] = cutoff_hz
    else:
        metrics["transfer_gain_db"] = response.gain_db[0]
    record = ExperimentRepository(args.experiment_database).create_experiment(
        name=args.experiment_name,
        circuit_type=config.circuit_type,
        parameters=parameters,
        simulation_time_seconds=simulation_time_seconds,
        metrics=metrics,
    )
    return record.experiment_id


def _run_sweep_workflow(args: argparse.Namespace) -> int:
    """Execute, rank, and export one automated parameter sweep."""
    config = load_sweep_config(args.sweep_config)
    output_dir = args.output_dir.resolve()
    started_at = monotonic()
    results = run_parameter_sweep(
        config,
        output_dir,
        executable=args.ngspice,
        timeout_seconds=args.timeout,
    )
    elapsed_seconds = monotonic() - started_at
    csv_path = save_sweep_results_csv(results, output_dir / "sweep_results.csv")
    successful_count = sum(result.succeeded for result in results)
    failed_count = len(results) - successful_count

    print(format_top_solutions(results, top_n=config.top_n))
    print(
        f"Sweep completed: {len(results)} combinations, "
        f"{successful_count} succeeded, {failed_count} failed."
    )
    print(f"Results CSV: {csv_path}")
    if successful_count == 0:
        raise CircuitPilotError(
            "all parameter combinations failed; inspect the CSV and run logs"
        )

    plot_path = plot_sweep_performance(
        results,
        output_dir / "parameter_performance.png",
        target_cutoff_frequency_hz=config.target_cutoff_frequency_hz,
    )
    print(f"Performance plot: {plot_path}")
    if args.experiment_name is not None:
        best_result = rank_solutions(results, top_n=1)[0]
        parameters = {
            "resistance_values_ohm": list(config.resistance_values_ohm),
            "capacitance_values_f": list(config.capacitance_values_f),
            "analysis": asdict(config.analysis),
        }
        metrics = {
            "target_cutoff_frequency_hz": config.target_cutoff_frequency_hz,
            "best_cutoff_frequency_hz": best_result.simulated_cutoff_frequency_hz,
            "best_relative_error": best_result.relative_error,
            "combination_count": float(len(results)),
            "success_count": float(successful_count),
            "failure_count": float(failed_count),
        }
        record = ExperimentRepository(args.experiment_database).create_experiment(
            name=args.experiment_name,
            circuit_type=config.circuit_type,
            parameters=parameters,
            simulation_time_seconds=elapsed_seconds,
            metrics=metrics,  # type: ignore[arg-type]
        )
        print(f"Experiment saved with ID {record.experiment_id}.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the complete parameterized circuit simulation workflow.

    Args:
        argv: Optional command-line arguments excluding the program name.

    Returns:
        Process-style status code: zero on success, one on expected failure.
    """
    args = build_parser().parse_args(argv)
    try:
        if args.command == "experiment":
            return _run_experiment_command(args)
        if args.sweep_config is not None:
            return _run_sweep_workflow(args)
        config = (
            load_circuit_config(args.config)
            if args.config is not None
            else _legacy_lowpass_config(args)
        )
        output_dir = args.output_dir.resolve()
        circuit_name = config.circuit_type.value
        netlist_path = output_dir / f"{circuit_name}.cir"
        data_path = output_dir / "ac_results.dat"
        log_path = output_dir / "ngspice.log"
        plot_path = output_dir / "bode.png"

        output_dir.mkdir(parents=True, exist_ok=True)
        data_path.unlink(missing_ok=True)
        write_netlist(netlist_path, data_path, config)
        simulation_result = run_ngspice(
            netlist_path,
            executable=args.ngspice,
            timeout_seconds=args.timeout,
            log_path=log_path,
        )
        response = parse_ac_output(data_path)
        cutoff_hz = _cutoff_for_config(config, response)
        titles = {
            CircuitType.RC_LOWPASS: "RC Low-Pass Filter Bode Plot",
            CircuitType.RC_HIGHPASS: "RC High-Pass Filter Bode Plot",
            CircuitType.VOLTAGE_DIVIDER: "Voltage Divider Frequency Response",
        }
        plot_bode(
            response,
            plot_path,
            cutoff_frequency_hz=cutoff_hz,
            title=titles[config.circuit_type],
            show=args.show,
        )
        experiment_id = _save_single_experiment(
            args,
            config,
            response,
            cutoff_hz,
            simulation_result.elapsed_seconds
            if args.experiment_name is not None
            else 0.0,
        )
    except (CircuitPilotError, OSError, ValueError) as exc:
        print(f"CircuitPilot error: {exc}", file=sys.stderr)
        return 1

    print(f"Simulation completed with {len(response)} AC samples.")
    print(f"Circuit type: {config.circuit_type.value}")
    if cutoff_hz is not None:
        print(f"-3 dB cutoff frequency: {cutoff_hz:.6g} Hz")
    else:
        print(f"Transfer gain: {response.gain_db[0]:.6g} dB")
    print(f"Bode plot: {plot_path}")
    if experiment_id is not None:
        print(f"Experiment saved with ID {experiment_id}.")
    return 0
