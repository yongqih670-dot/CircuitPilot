"""Execution, ranking, CSV export, and visualization for parameter sweeps."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Sequence

from circuitpilot.analysis import find_cutoff_frequency, find_highpass_cutoff_frequency
from circuitpilot.circuit_config import (
    CircuitConfig,
    CircuitType,
    RCHighPassConfig,
    RCLowPassConfig,
)
from circuitpilot.exceptions import CircuitPilotError, SweepError
from circuitpilot.netlist_generator import write_netlist
from circuitpilot.parser import parse_ac_output
from circuitpilot.simulator import resolve_ngspice_executable, run_ngspice
from circuitpilot.sweep_config import (
    ParameterCombination,
    SweepConfig,
    generate_parameter_combinations,
)


@dataclass(frozen=True, slots=True)
class SweepResult:
    """Outcome and relative error for one simulated parameter combination."""

    run_index: int
    resistance_ohm: float
    capacitance_f: float
    target_cutoff_frequency_hz: float
    simulated_cutoff_frequency_hz: float | None
    relative_error: float | None
    status: str
    error_message: str = ""

    def __post_init__(self) -> None:
        """Keep exported and ranked result rows internally consistent."""
        if self.run_index <= 0:
            raise ValueError("run_index must be positive")
        if not isfinite(self.resistance_ohm) or self.resistance_ohm <= 0:
            raise ValueError("resistance_ohm must be finite and positive")
        if not isfinite(self.capacitance_f) or self.capacitance_f <= 0:
            raise ValueError("capacitance_f must be finite and positive")
        if (
            not isfinite(self.target_cutoff_frequency_hz)
            or self.target_cutoff_frequency_hz <= 0
        ):
            raise ValueError("target_cutoff_frequency_hz must be finite and positive")
        if self.status not in {"success", "failed"}:
            raise ValueError("status must be either 'success' or 'failed'")
        if self.status == "success":
            if (
                self.simulated_cutoff_frequency_hz is None
                or not isfinite(self.simulated_cutoff_frequency_hz)
                or self.simulated_cutoff_frequency_hz <= 0
            ):
                raise ValueError("successful results require a positive cutoff")
            if (
                self.relative_error is None
                or not isfinite(self.relative_error)
                or self.relative_error < 0
            ):
                raise ValueError("successful results require a non-negative error")

    @property
    def succeeded(self) -> bool:
        """Return whether simulation and cutoff extraction both succeeded."""
        return self.status == "success"


def calculate_relative_error(simulated: float, target: float) -> float:
    """Return ``abs(simulated - target) / target`` for positive values."""
    if not isfinite(simulated) or not isfinite(target) or simulated <= 0 or target <= 0:
        raise ValueError(
            "simulated and target cutoff frequencies must be finite and positive"
        )
    return abs(simulated - target) / target


def _build_circuit_config(
    sweep_config: SweepConfig, combination: ParameterCombination
) -> CircuitConfig:
    """Convert one sweep pair into the existing simulation configuration."""
    circuit_class = (
        RCLowPassConfig
        if sweep_config.circuit_type is CircuitType.RC_LOWPASS
        else RCHighPassConfig
    )
    return CircuitConfig(
        circuit=circuit_class(
            resistance_ohm=combination.resistance_ohm,
            capacitance_f=combination.capacitance_f,
        ),
        analysis=sweep_config.analysis,
    )


def run_parameter_sweep(
    config: SweepConfig,
    output_directory: str | Path,
    *,
    executable: str = "ngspice",
    timeout_seconds: float = 60.0,
) -> tuple[SweepResult, ...]:
    """Generate and simulate every parameter combination sequentially.

    Each combination receives its own ``runs/run_NNNN`` directory. Expected
    per-run failures are recorded in the returned results so one bad point does
    not discard the rest of the experiment.

    Args:
        config: Validated target and parameter space.
        output_directory: Root directory for generated run artifacts.
        executable: ngspice executable name or full path.
        timeout_seconds: Per-combination ngspice timeout.

    Returns:
        One result per Cartesian-product combination, in deterministic order.

    Raises:
        SweepError: If the shared output directory cannot be created.
    """
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    resolved_executable = resolve_ngspice_executable(executable)
    if resolved_executable is None:
        raise SweepError(
            f"ngspice executable '{executable}' was not found; "
            "install ngspice or pass --ngspice with its full path"
        )
    output_root = Path(output_directory).resolve()
    runs_directory = output_root / "runs"
    try:
        runs_directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SweepError(
            f"failed to create sweep output directory '{runs_directory}': {exc}"
        ) from exc

    combinations = generate_parameter_combinations(config)
    index_width = max(4, len(str(len(combinations))))
    results: list[SweepResult] = []

    for run_index, combination in enumerate(combinations, start=1):
        run_directory = runs_directory / f"run_{run_index:0{index_width}d}"
        netlist_path = run_directory / f"{config.circuit_type.value}.cir"
        data_path = run_directory / "ac_results.dat"
        log_path = run_directory / "ngspice.log"
        try:
            run_directory.mkdir(parents=True, exist_ok=True)
            data_path.unlink(missing_ok=True)
            circuit_config = _build_circuit_config(config, combination)
            write_netlist(netlist_path, data_path, circuit_config)
            run_ngspice(
                netlist_path,
                executable=resolved_executable,
                timeout_seconds=timeout_seconds,
                log_path=log_path,
            )
            response = parse_ac_output(data_path)
            if config.circuit_type is CircuitType.RC_LOWPASS:
                simulated_cutoff = find_cutoff_frequency(
                    response.frequency_hz, response.gain_db
                )
            else:
                simulated_cutoff = find_highpass_cutoff_frequency(
                    response.frequency_hz, response.gain_db
                )
            relative_error = calculate_relative_error(
                simulated_cutoff, config.target_cutoff_frequency_hz
            )
        except (CircuitPilotError, OSError, ValueError) as exc:
            results.append(
                SweepResult(
                    run_index=run_index,
                    resistance_ohm=combination.resistance_ohm,
                    capacitance_f=combination.capacitance_f,
                    target_cutoff_frequency_hz=config.target_cutoff_frequency_hz,
                    simulated_cutoff_frequency_hz=None,
                    relative_error=None,
                    status="failed",
                    error_message=str(exc),
                )
            )
            continue

        results.append(
            SweepResult(
                run_index=run_index,
                resistance_ohm=combination.resistance_ohm,
                capacitance_f=combination.capacitance_f,
                target_cutoff_frequency_hz=config.target_cutoff_frequency_hz,
                simulated_cutoff_frequency_hz=simulated_cutoff,
                relative_error=relative_error,
                status="success",
            )
        )

    return tuple(results)


def rank_solutions(
    results: Sequence[SweepResult], *, top_n: int = 10
) -> tuple[SweepResult, ...]:
    """Return successful solutions ordered by relative error, R, then C."""
    if isinstance(top_n, bool) or not isinstance(top_n, int) or top_n <= 0:
        raise ValueError("top_n must be a positive integer")
    successful = (result for result in results if result.succeeded)
    ranked = sorted(
        successful,
        key=lambda result: (
            result.relative_error if result.relative_error is not None else float("inf"),
            result.resistance_ohm,
            result.capacitance_f,
        ),
    )
    return tuple(ranked[:top_n])


def format_top_solutions(
    results: Sequence[SweepResult], *, top_n: int = 10
) -> str:
    """Format a compact human-readable Top-N ranking table."""
    ranked = rank_solutions(results, top_n=top_n)
    lines = [
        f"Top {top_n} solutions",
        "Rank  R (ohm)       C (F)         Cutoff (Hz)    Relative error",
    ]
    if not ranked:
        lines.append("No successful simulations.")
        return "\n".join(lines)
    for rank, result in enumerate(ranked, start=1):
        lines.append(
            f"{rank:<5} "
            f"{result.resistance_ohm:<13.6g} "
            f"{result.capacitance_f:<13.6g} "
            f"{result.simulated_cutoff_frequency_hz:<14.6g} "
            f"{result.relative_error:.6g}"
        )
    return "\n".join(lines)


def save_sweep_results_csv(
    results: Sequence[SweepResult], output_path: str | Path
) -> Path:
    """Save all experiment results, including failures, to a UTF-8 CSV file."""
    destination = Path(output_path).resolve()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        ranked_all = rank_solutions(results, top_n=max(1, len(results)))
        rank_by_run = {
            result.run_index: rank for rank, result in enumerate(ranked_all, start=1)
        }
        with destination.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(
                (
                    "run_index",
                    "rank",
                    "resistance_ohm",
                    "capacitance_f",
                    "target_cutoff_frequency_hz",
                    "simulated_cutoff_frequency_hz",
                    "relative_error",
                    "status",
                    "error_message",
                )
            )
            for result in results:
                writer.writerow(
                    (
                        result.run_index,
                        rank_by_run.get(result.run_index, ""),
                        f"{result.resistance_ohm:.12g}",
                        f"{result.capacitance_f:.12g}",
                        f"{result.target_cutoff_frequency_hz:.12g}",
                        ""
                        if result.simulated_cutoff_frequency_hz is None
                        else f"{result.simulated_cutoff_frequency_hz:.12g}",
                        ""
                        if result.relative_error is None
                        else f"{result.relative_error:.12g}",
                        result.status,
                        result.error_message,
                    )
                )
    except OSError as exc:
        raise SweepError(f"failed to save sweep CSV '{destination}': {exc}") from exc
    return destination


def plot_sweep_performance(
    results: Sequence[SweepResult],
    output_path: str | Path,
    *,
    target_cutoff_frequency_hz: float,
) -> Path:
    """Plot resistance versus simulated cutoff, one curve per capacitance."""
    successful = [result for result in results if result.succeeded]
    if not successful:
        raise SweepError("cannot plot a sweep with no successful simulations")
    if (
        not isfinite(target_cutoff_frequency_hz)
        or target_cutoff_frequency_hz <= 0
    ):
        raise ValueError("target_cutoff_frequency_hz must be finite and positive")

    import matplotlib.pyplot as plt

    destination = Path(output_path).resolve()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise SweepError(
            f"failed to create sweep plot directory '{destination.parent}': {exc}"
        ) from exc

    grouped: dict[float, list[SweepResult]] = {}
    for result in successful:
        grouped.setdefault(result.capacitance_f, []).append(result)

    figure, axis = plt.subplots(figsize=(9, 6), constrained_layout=True)
    try:
        for capacitance, group in sorted(grouped.items()):
            ordered = sorted(group, key=lambda result: result.resistance_ohm)
            axis.plot(
                [result.resistance_ohm for result in ordered],
                [result.simulated_cutoff_frequency_hz for result in ordered],
                marker="o",
                markersize=3,
                linewidth=1.2,
                label=f"C = {capacitance:.4g} F",
            )
        axis.axhline(
            target_cutoff_frequency_hz,
            color="#c44e52",
            linestyle="--",
            linewidth=1.5,
            label=f"Target = {target_cutoff_frequency_hz:.4g} Hz",
        )
        axis.set_xscale("log")
        axis.set_yscale("log")
        axis.set_xlabel("Resistance (ohm)")
        axis.set_ylabel("Simulated cutoff frequency (Hz)")
        axis.set_title("Parameter Sweep: Component Values vs Performance")
        axis.grid(True, which="both", linestyle=":", alpha=0.6)
        axis.legend(loc="best", fontsize="small")
        try:
            figure.savefig(destination, dpi=150)
        except (OSError, ValueError) as exc:
            raise SweepError(
                f"failed to save sweep performance plot '{destination}': {exc}"
            ) from exc
    finally:
        plt.close(figure)
    return destination
