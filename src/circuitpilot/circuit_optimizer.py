"""Simulation-driven circuit objectives, optimization, and history artifacts."""

from __future__ import annotations

from bisect import bisect_left
import cmath
import csv
from dataclasses import asdict, dataclass
import json
from math import isfinite, log10, radians
from pathlib import Path
from time import monotonic
from typing import Any, Sequence

from scipy.optimize import differential_evolution

from circuitpilot.analysis import find_cutoff_frequency, find_highpass_cutoff_frequency
from circuitpilot.circuit_config import (
    CircuitConfig,
    CircuitType,
    RCHighPassConfig,
    RCLowPassConfig,
)
from circuitpilot.exceptions import CircuitPilotError, OptimizationError
from circuitpilot.netlist_generator import write_netlist
from circuitpilot.optimization_config import (
    ObjectiveGoal,
    ObjectiveMetric,
    OptimizationConfig,
)
from circuitpilot.parser import ACAnalysisResult, parse_ac_output
from circuitpilot.simulator import resolve_ngspice_executable, run_ngspice


FAILED_OBJECTIVE_PENALTY = 1e100


@dataclass(frozen=True, slots=True)
class OptimizationEvaluation:
    """One optimizer-requested parameter pair and its simulation outcome."""

    evaluation_index: int
    resistance_ohm: float
    capacitance_f: float
    metric_value: float | None
    objective_value: float
    status: str
    simulation_time_seconds: float
    run_directory: str
    error_message: str = ""

    def __post_init__(self) -> None:
        """Keep history rows valid for ranking and persistence."""
        if self.evaluation_index <= 0:
            raise ValueError("evaluation_index must be positive")
        if not isfinite(self.resistance_ohm) or self.resistance_ohm <= 0:
            raise ValueError("resistance_ohm must be finite and positive")
        if not isfinite(self.capacitance_f) or self.capacitance_f <= 0:
            raise ValueError("capacitance_f must be finite and positive")
        if self.status not in {"success", "failed"}:
            raise ValueError("status must be 'success' or 'failed'")
        if not isfinite(self.objective_value):
            raise ValueError("objective_value must be finite")
        if (
            not isfinite(self.simulation_time_seconds)
            or self.simulation_time_seconds < 0
        ):
            raise ValueError("simulation_time_seconds must be finite and non-negative")
        if self.status == "success":
            if self.metric_value is None or not isfinite(self.metric_value):
                raise ValueError("successful evaluations require a finite metric")
        elif self.metric_value is not None:
            raise ValueError("failed evaluations must not contain a metric")

    @property
    def succeeded(self) -> bool:
        """Return whether simulation and metric extraction succeeded."""
        return self.status == "success"


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Best evaluation and complete history returned by SciPy optimization."""

    best_evaluation: OptimizationEvaluation
    evaluations: tuple[OptimizationEvaluation, ...]
    optimizer_success: bool
    optimizer_message: str
    iteration_count: int
    function_evaluation_count: int
    total_time_seconds: float

    @property
    def successful_count(self) -> int:
        """Count successful SPICE/metric evaluations."""
        return sum(evaluation.succeeded for evaluation in self.evaluations)

    @property
    def failed_count(self) -> int:
        """Count failed evaluations retained in history."""
        return len(self.evaluations) - self.successful_count


def _interpolate_at_frequency(
    frequency_hz: Sequence[float],
    values: Sequence[float],
    target_frequency_hz: float,
) -> float:
    """Interpolate a response value on the logarithmic frequency axis."""
    if len(frequency_hz) != len(values) or len(frequency_hz) < 2:
        raise OptimizationError("response arrays must have equal lengths of at least two")
    if not isfinite(target_frequency_hz) or target_frequency_hz <= 0:
        raise OptimizationError("evaluation frequency must be finite and positive")
    if target_frequency_hz < frequency_hz[0] or target_frequency_hz > frequency_hz[-1]:
        raise OptimizationError(
            f"evaluation frequency {target_frequency_hz:.6g} Hz is outside the "
            f"simulated range {frequency_hz[0]:.6g}..{frequency_hz[-1]:.6g} Hz"
        )
    index = bisect_left(frequency_hz, target_frequency_hz)
    if index < len(frequency_hz) and frequency_hz[index] == target_frequency_hz:
        return float(values[index])
    if index == 0 or index == len(frequency_hz):
        raise OptimizationError("evaluation frequency cannot be interpolated")
    lower_frequency = frequency_hz[index - 1]
    upper_frequency = frequency_hz[index]
    if (
        not isfinite(lower_frequency)
        or not isfinite(upper_frequency)
        or lower_frequency <= 0
        or upper_frequency <= lower_frequency
    ):
        raise OptimizationError("response frequencies must be positive and increasing")
    lower_value = values[index - 1]
    upper_value = values[index]
    if not isfinite(lower_value) or not isfinite(upper_value):
        raise OptimizationError("response values must be finite")
    fraction = (log10(target_frequency_hz) - log10(lower_frequency)) / (
        log10(upper_frequency) - log10(lower_frequency)
    )
    return float(lower_value + fraction * (upper_value - lower_value))


def evaluate_response_metric(
    config: OptimizationConfig,
    response: ACAnalysisResult,
    *,
    resistance_ohm: float,
) -> float:
    """Evaluate the configured bandwidth, gain, or resistor-power metric.

    Gain is measured in dB at ``evaluation_frequency_hz``. Power is the
    resistor's average sinusoidal dissipation in watts for a 1 V peak AC
    source. Bandwidth is the interpolated -3 dB cutoff frequency in hertz.

    Args:
        config: Optimization and objective definition.
        response: Parsed ngspice AC response for the candidate circuit.
        resistance_ohm: Candidate resistor value used by the power formula.

    Returns:
        Metric in hertz, decibels, or watts according to the objective.
    """
    metric = config.objective.metric
    if metric is ObjectiveMetric.BANDWIDTH:
        if config.circuit_type is CircuitType.RC_LOWPASS:
            return find_cutoff_frequency(response.frequency_hz, response.gain_db)
        return find_highpass_cutoff_frequency(
            response.frequency_hz, response.gain_db
        )

    evaluation_frequency = config.objective.evaluation_frequency_hz
    assert evaluation_frequency is not None
    gain_db = _interpolate_at_frequency(
        response.frequency_hz, response.gain_db, evaluation_frequency
    )
    if metric is ObjectiveMetric.GAIN:
        return gain_db

    phase_deg = _interpolate_at_frequency(
        response.frequency_hz, response.phase_deg, evaluation_frequency
    )
    transfer = cmath.rect(10.0 ** (gain_db / 20.0), radians(phase_deg))
    resistor_voltage = (
        1.0 - transfer
        if config.circuit_type is CircuitType.RC_LOWPASS
        else transfer
    )
    return abs(resistor_voltage) ** 2 / (2.0 * resistance_ohm)


def metric_to_objective(config: OptimizationConfig, metric_value: float) -> float:
    """Convert a physical metric to the scalar minimized by SciPy."""
    if not isfinite(metric_value):
        raise OptimizationError("metric value must be finite")
    objective = config.objective
    if objective.goal is ObjectiveGoal.TARGET:
        assert objective.target_value is not None
        return abs(metric_value - objective.target_value) / objective.target_value
    if objective.goal is ObjectiveGoal.MAXIMIZE:
        return -metric_value
    return metric_value


def _circuit_config(
    config: OptimizationConfig,
    resistance_ohm: float,
    capacitance_f: float,
) -> CircuitConfig:
    """Build one existing typed circuit configuration for a candidate."""
    circuit_class = (
        RCLowPassConfig
        if config.circuit_type is CircuitType.RC_LOWPASS
        else RCHighPassConfig
    )
    return CircuitConfig(
        circuit=circuit_class(
            resistance_ohm=resistance_ohm,
            capacitance_f=capacitance_f,
        ),
        analysis=config.analysis,
    )


def run_circuit_optimization(
    config: OptimizationConfig,
    output_directory: str | Path,
    *,
    executable: str = "ngspice",
    timeout_seconds: float = 60.0,
) -> OptimizationResult:
    """Optimize R and C through repeated ngspice AC simulations.

    Differential evolution proposes continuous R/C coordinates. Every call is
    persisted in ``runs/evaluation_NNNNN`` before the metric is returned to
    SciPy. Expected per-candidate failures receive a finite penalty and remain
    in the final history.

    Args:
        config: Validated parameter ranges, objective, and solver settings.
        output_directory: Root for all generated simulation artifacts.
        executable: ngspice name or full path.
        timeout_seconds: Maximum duration of each SPICE process.

    Returns:
        Best successful evaluation plus the complete ordered history.

    Raises:
        OptimizationError: If ngspice is unavailable, SciPy fails to run, or
            no candidate produces a valid metric.
    """
    if not isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be finite and positive")
    resolved_executable = resolve_ngspice_executable(executable)
    if resolved_executable is None:
        raise OptimizationError(
            f"ngspice executable '{executable}' was not found; install ngspice "
            "or pass --ngspice with its full path"
        )
    output_root = Path(output_directory).resolve()
    runs_directory = output_root / "runs"
    try:
        runs_directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OptimizationError(
            f"failed to create optimization output '{runs_directory}': {exc}"
        ) from exc

    history: list[OptimizationEvaluation] = []
    started_at = monotonic()

    def objective_function(coordinates: Sequence[float]) -> float:
        evaluation_index = len(history) + 1
        resistance, capacitance = config.decode_parameters(
            (float(coordinates[0]), float(coordinates[1]))
        )
        run_name = f"evaluation_{evaluation_index:05d}"
        run_directory = runs_directory / run_name
        portable_run_directory = (Path("runs") / run_name).as_posix()
        netlist_path = run_directory / f"{config.circuit_type.value}.cir"
        data_path = run_directory / "ac_results.dat"
        log_path = run_directory / "ngspice.log"
        evaluation_started = monotonic()
        try:
            run_directory.mkdir(parents=True, exist_ok=True)
            data_path.unlink(missing_ok=True)
            write_netlist(
                netlist_path,
                data_path,
                _circuit_config(config, resistance, capacitance),
            )
            run_ngspice(
                netlist_path,
                executable=resolved_executable,
                timeout_seconds=timeout_seconds,
                log_path=log_path,
            )
            response = parse_ac_output(data_path)
            metric_value = evaluate_response_metric(
                config, response, resistance_ohm=resistance
            )
            objective_value = metric_to_objective(config, metric_value)
        except (CircuitPilotError, OSError, ValueError) as exc:
            history.append(
                OptimizationEvaluation(
                    evaluation_index=evaluation_index,
                    resistance_ohm=resistance,
                    capacitance_f=capacitance,
                    metric_value=None,
                    objective_value=FAILED_OBJECTIVE_PENALTY,
                    status="failed",
                    simulation_time_seconds=monotonic() - evaluation_started,
                    run_directory=portable_run_directory,
                    error_message=str(exc),
                )
            )
            return FAILED_OBJECTIVE_PENALTY

        history.append(
            OptimizationEvaluation(
                evaluation_index=evaluation_index,
                resistance_ohm=resistance,
                capacitance_f=capacitance,
                metric_value=metric_value,
                objective_value=objective_value,
                status="success",
                simulation_time_seconds=monotonic() - evaluation_started,
                run_directory=portable_run_directory,
            )
        )
        return objective_value

    bounds = (
        config.resistance.optimizer_bounds,
        config.capacitance.optimizer_bounds,
    )
    try:
        scipy_result: Any = differential_evolution(
            objective_function,
            bounds=bounds,
            maxiter=config.optimizer.max_iterations,
            popsize=config.optimizer.population_size,
            tol=config.optimizer.tolerance,
            seed=config.optimizer.seed,
            polish=config.optimizer.polish,
            workers=1,
            updating="immediate",
        )
    except Exception as exc:
        raise OptimizationError(f"SciPy optimizer failed: {exc}") from exc

    successful = [evaluation for evaluation in history if evaluation.succeeded]
    if not successful:
        raise OptimizationError(
            "all optimization evaluations failed; inspect runs/evaluation_* logs"
        )
    best = min(
        successful,
        key=lambda evaluation: (evaluation.objective_value, evaluation.evaluation_index),
    )
    return OptimizationResult(
        best_evaluation=best,
        evaluations=tuple(history),
        optimizer_success=bool(scipy_result.success),
        optimizer_message=str(scipy_result.message),
        iteration_count=int(scipy_result.nit),
        function_evaluation_count=int(scipy_result.nfev),
        total_time_seconds=monotonic() - started_at,
    )


def save_optimization_history_csv(
    result: OptimizationResult, output_path: str | Path
) -> Path:
    """Save every successful and failed objective evaluation to CSV."""
    destination = Path(output_path).resolve()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        best_so_far = float("inf")
        with destination.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                (
                    "evaluation_index",
                    "resistance_ohm",
                    "capacitance_f",
                    "metric_value",
                    "objective_value",
                    "best_objective_so_far",
                    "status",
                    "simulation_time_seconds",
                    "run_directory",
                    "error_message",
                )
            )
            for evaluation in result.evaluations:
                best_so_far = min(best_so_far, evaluation.objective_value)
                writer.writerow(
                    (
                        evaluation.evaluation_index,
                        f"{evaluation.resistance_ohm:.12g}",
                        f"{evaluation.capacitance_f:.12g}",
                        ""
                        if evaluation.metric_value is None
                        else f"{evaluation.metric_value:.12g}",
                        f"{evaluation.objective_value:.12g}",
                        f"{best_so_far:.12g}",
                        evaluation.status,
                        f"{evaluation.simulation_time_seconds:.12g}",
                        evaluation.run_directory,
                        evaluation.error_message,
                    )
                )
    except OSError as exc:
        raise OptimizationError(
            f"failed to save optimization history '{destination}': {exc}"
        ) from exc
    return destination


def save_optimization_summary_json(
    config: OptimizationConfig,
    result: OptimizationResult,
    output_path: str | Path,
) -> Path:
    """Save a machine-readable best result and solver summary."""
    destination = Path(output_path).resolve()
    best = result.best_evaluation
    summary = {
        "circuit_type": config.circuit_type.value,
        "objective": {
            "metric": config.objective.metric.value,
            "goal": config.objective.goal.value,
            "target_value": config.objective.target_value,
            "evaluation_frequency_hz": config.objective.evaluation_frequency_hz,
        },
        "best": asdict(best),
        "optimizer": {
            "success": result.optimizer_success,
            "message": result.optimizer_message,
            "iteration_count": result.iteration_count,
            "function_evaluation_count": result.function_evaluation_count,
            "recorded_evaluation_count": len(result.evaluations),
            "successful_count": result.successful_count,
            "failed_count": result.failed_count,
            "total_time_seconds": result.total_time_seconds,
        },
    }
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise OptimizationError(
            f"failed to save optimization summary '{destination}': {exc}"
        ) from exc
    return destination


def plot_optimization_progress(
    config: OptimizationConfig,
    result: OptimizationResult,
    output_path: str | Path,
    *,
    show: bool = False,
) -> Path:
    """Plot raw/best objective and physical metric over all evaluations."""
    successful = [evaluation for evaluation in result.evaluations if evaluation.succeeded]
    if not successful:
        raise OptimizationError("cannot plot optimization without successful evaluations")

    import matplotlib.pyplot as plt

    destination = Path(output_path).resolve()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OptimizationError(
            f"failed to create optimization plot directory '{destination.parent}': {exc}"
        ) from exc

    indices = [evaluation.evaluation_index for evaluation in successful]
    objectives = [evaluation.objective_value for evaluation in successful]
    metrics = [float(evaluation.metric_value) for evaluation in successful]
    best_values: list[float] = []
    current_best = float("inf")
    for value in objectives:
        current_best = min(current_best, value)
        best_values.append(current_best)

    figure, (objective_axis, metric_axis) = plt.subplots(
        2, 1, figsize=(9, 8), sharex=True, constrained_layout=True
    )
    try:
        objective_axis.plot(
            indices,
            objectives,
            color="#4c72b0",
            marker=".",
            alpha=0.45,
            linewidth=0.8,
            label="Evaluation objective",
        )
        objective_axis.plot(
            indices,
            best_values,
            color="#c44e52",
            linewidth=2.0,
            label="Best objective so far",
        )
        objective_axis.set_ylabel("Minimized objective")
        objective_axis.set_title("CircuitPilot Optimization Progress")
        objective_axis.grid(True, linestyle=":", alpha=0.6)
        objective_axis.legend(loc="best")

        metric_axis.plot(
            indices,
            metrics,
            color="#55a868",
            marker="o",
            markersize=3,
            linewidth=1.0,
            label=f"{config.objective.metric.value} metric",
        )
        if config.objective.target_value is not None:
            metric_axis.axhline(
                config.objective.target_value,
                color="#c44e52",
                linestyle="--",
                linewidth=1.5,
                label=f"Target = {config.objective.target_value:.6g}",
            )
        metric_axis.set_xlabel("Objective evaluation")
        metric_axis.set_ylabel(
            {
                ObjectiveMetric.BANDWIDTH: "Bandwidth (Hz)",
                ObjectiveMetric.GAIN: "Gain (dB)",
                ObjectiveMetric.POWER: "Power (W)",
            }[config.objective.metric]
        )
        metric_axis.grid(True, linestyle=":", alpha=0.6)
        metric_axis.legend(loc="best")
        try:
            figure.savefig(destination, dpi=150)
        except (OSError, ValueError) as exc:
            raise OptimizationError(
                f"failed to save optimization plot '{destination}': {exc}"
            ) from exc
        if show:
            plt.show()
    finally:
        plt.close(figure)
    return destination
