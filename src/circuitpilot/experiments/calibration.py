"""Deterministic, non-optimizer calibration for transistor benchmarks."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from hashlib import sha256
from itertools import product
import json
from math import exp, log, log2
from pathlib import Path
import shutil
from time import monotonic
from typing import Any, Mapping, Sequence

import yaml
from scipy.stats import qmc

from circuitpilot.exceptions import CircuitPilotError, ConfigError, ResearchExperimentError, SimulationError
from circuitpilot.experiments.analyzer import (
    AnalysisOutcome,
    Sky130CommonSourceAnalyzer,
    Sky130DifferentialAmplifierAnalyzer,
)
from circuitpilot.experiments.config import ExperimentConfig, load_experiment_config, write_experiment_config
from circuitpilot.experiments.objectives import ObjectiveEvaluator
from circuitpilot.experiments.simulation import (
    CommonSourceNgspiceSimulator,
    Sky130CommonSourceNgspiceSimulator,
    Sky130DifferentialAmplifierNgspiceSimulator,
)
from circuitpilot.common_source import analyze_common_source
from circuitpilot.sky130_common_source import Sky130CommonSourceCircuitConfig
from circuitpilot.sky130_differential_amplifier import (
    Sky130DifferentialAmplifierCircuitConfig,
)
from circuitpilot.research_artifacts import write_research_manifest
from circuitpilot.run_directory import prepare_research_run_directory


CALIBRATION_COLUMNS = (
    "iteration",
    "parameters",
    "simulation_status",
    "measurement_status",
    "bandwidth_status",
    "bandwidth_lower_bound_hz",
    "cmrr_status",
    "cmrr_lower_bound_db",
    "failure_type",
    "error_message",
    "ngspice_return_code",
    "timed_out",
    "raw_metrics",
    "is_feasible_frozen_spec",
    "constraint_violation_frozen_spec",
    "simulation_time",
    "ngspice_called",
    "ngspice_process_calls",
    "analysis_calls",
    "evidence_directory",
)


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    """Evidence paths and exact call counts for one deterministic grid."""

    run_id: str
    output_directory: Path
    csv_path: Path
    grid_sha256: str
    ngspice_calls: int
    successful: int
    failed: int
    analysis_calls: int = 0


def load_calibration_grid(
    path: str | Path, config: ExperimentConfig
) -> dict[str, tuple[float | int, ...]]:
    """Load and validate an explicit deterministic grid against search space."""
    source = Path(path).resolve()
    try:
        value = yaml.safe_load(source.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"failed to read calibration grid '{source}': {exc}") from exc
    if not isinstance(value, Mapping) or set(value) != {"grid"}:
        raise ConfigError("calibration grid root must contain only 'grid'")
    raw_grid = value["grid"]
    if not isinstance(raw_grid, Mapping):
        raise ConfigError("calibration grid must be a mapping")
    if set(raw_grid) != set(config.search_space_by_name):
        raise ConfigError("calibration grid parameters must exactly match search_space")
    grid: dict[str, tuple[float | int, ...]] = {}
    for parameter in config.search_space:
        values = raw_grid[parameter.name]
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)) or not values:
            raise ConfigError(f"calibration grid.{parameter.name} must be a non-empty list")
        normalized = tuple(values)
        if len(set(normalized)) != len(normalized):
            raise ConfigError(f"calibration grid.{parameter.name} values must be unique")
        for item in normalized:
            if not parameter.contains(item):
                raise ConfigError(
                    f"calibration grid.{parameter.name} contains an out-of-range value"
                )
        grid[parameter.name] = normalized
    return grid


def _grid_hash(grid: Mapping[str, Sequence[float | int]]) -> str:
    encoded = json.dumps(grid, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return sha256(encoded).hexdigest()


def _write_rows(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=CALIBRATION_COLUMNS)
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        **row,
                        "parameters": json.dumps(row["parameters"], sort_keys=True, separators=(",", ":"), allow_nan=False),
                        "raw_metrics": json.dumps(row["raw_metrics"], sort_keys=True, separators=(",", ":"), allow_nan=False),
                        "timed_out": str(bool(row["timed_out"])).lower(),
                        "ngspice_called": str(bool(row["ngspice_called"])).lower(),
                        "ngspice_process_calls": int(
                            row.get("ngspice_process_calls", bool(row["ngspice_called"]))
                        ),
                        "analysis_calls": int(row.get("analysis_calls", 0)),
                        "cmrr_status": row.get("cmrr_status", ""),
                        "cmrr_lower_bound_db": (
                            ""
                            if row.get("cmrr_lower_bound_db") in (None, "")
                            else f"{float(row['cmrr_lower_bound_db']):.17g}"
                        ),
                        "is_feasible_frozen_spec": (
                            "" if row["is_feasible_frozen_spec"] is None else str(bool(row["is_feasible_frozen_spec"])).lower()
                        ),
                        "constraint_violation_frozen_spec": (
                            "" if row["constraint_violation_frozen_spec"] is None else f"{float(row['constraint_violation_frozen_spec']):.17g}"
                        ),
                    }
                )
        temporary.replace(path)
    except (OSError, TypeError, ValueError) as exc:
        temporary.unlink(missing_ok=True)
        raise ResearchExperimentError(f"failed to write calibration CSV '{path}': {exc}") from exc


def run_common_source_calibration(
    config: ExperimentConfig,
    grid: Mapping[str, Sequence[float | int]],
    *,
    published_csv: str | Path | None = None,
) -> CalibrationResult:
    """Execute each deterministic grid point with exactly one real ngspice call."""
    if config.circuit_name not in {"common_source", "sky130_common_source"}:
        raise ValueError("calibration supports transistor common-source benchmarks only")
    run = prepare_research_run_directory(None, resume=False, default_root=config.output_dir)
    (run.path / "runs").mkdir(parents=True, exist_ok=True)
    write_experiment_config(config, run.path / "calibration_config.yaml")
    ordered_names = tuple(parameter.name for parameter in config.search_space)
    rows: list[dict[str, Any]] = []
    ngspice_calls = 0
    simulator = (
        CommonSourceNgspiceSimulator(config)
        if config.circuit_name == "common_source"
        else Sky130CommonSourceNgspiceSimulator(config)
    )
    sky_analyzer = (
        Sky130CommonSourceAnalyzer(config)
        if config.circuit_name == "sky130_common_source"
        else None
    )
    started = monotonic()
    for iteration, values in enumerate(product(*(grid[name] for name in ordered_names)), start=1):
        parameters = dict(zip(ordered_names, values))
        config.validate_parameters(parameters)
        evidence = run.path / "runs" / f"calibration_{iteration:04d}"
        candidate_started = monotonic()
        called = False

        def mark_call() -> None:
            nonlocal ngspice_calls, called
            ngspice_calls += 1
            called = True

        status = "success"
        failure_type = None
        error_message = None
        returncode = None
        timed_out = False
        metrics: dict[str, float | None] = {}
        measurement_status = None
        bandwidth_status = None
        bandwidth_lower_bound_hz = None
        try:
            simulation = simulator.evaluate(parameters, evidence, mark_call)
            if sky_analyzer is not None:
                outcome = sky_analyzer.extract(simulation, parameters)
                assert isinstance(outcome, AnalysisOutcome)
                metrics = outcome.metrics
                measurement_status = outcome.measurement_status
                bandwidth_status = outcome.bandwidth_status
                bandwidth_lower_bound_hz = outcome.bandwidth_lower_bound_hz
                if measurement_status != "complete":
                    status = "measurement_incomplete"
                    failure_type = (
                        "InvalidResponse"
                        if measurement_status == "invalid_response"
                        else "AnalysisError"
                    )
                    error_message = outcome.message
            else:
                if simulation.operating_point is None:
                    raise ResearchExperimentError("calibration simulation has no operating point")
                metrics = analyze_common_source(
                    simulation.response, simulation.operating_point
                ).to_dict()
                metrics.update(simulation.operating_point.device_quantities)
                measurement_status = "complete"
        except (CircuitPilotError, OSError, ValueError) as exc:
            status = "simulation_failed" if isinstance(exc, SimulationError) else "evaluation_failed"
            failure_type = type(exc).__name__
            error_message = str(exc)
            if isinstance(exc, SimulationError):
                returncode = exc.returncode
                timed_out = exc.timed_out
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / "calibration_error.txt").write_text(str(exc) + "\n", encoding="utf-8")
        rows.append(
            {
                "iteration": iteration,
                "parameters": parameters,
                "simulation_status": status,
                "measurement_status": measurement_status or "",
                "bandwidth_status": bandwidth_status or "",
                "bandwidth_lower_bound_hz": (
                    "" if bandwidth_lower_bound_hz is None else bandwidth_lower_bound_hz
                ),
                "failure_type": failure_type or "",
                "error_message": error_message or "",
                "ngspice_return_code": "" if returncode is None else returncode,
                "timed_out": timed_out,
                "raw_metrics": metrics,
                "is_feasible_frozen_spec": None,
                "constraint_violation_frozen_spec": None,
                "simulation_time": monotonic() - candidate_started,
                "ngspice_called": called,
                "evidence_directory": (Path("runs") / evidence.name).as_posix(),
            }
        )
    if ngspice_calls != len(rows):
        raise ResearchExperimentError(
            "calibration did not launch exactly one ngspice call per grid point"
        )
    csv_path = run.path / "common_source_calibration.csv"
    _write_rows(csv_path, rows)
    if published_csv is not None:
        destination = Path(published_csv).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(csv_path, destination)
    grid_hash = _grid_hash(grid)
    successful = sum(row["simulation_status"] == "success" for row in rows)
    model = config.circuit_config.model if config.circuit_config is not None else None
    write_research_manifest(
        run.path,
        workflow="calibration",
        circuit_type=config.circuit_name,
        configuration={**config.to_dict(), "calibration_grid": {key: list(value) for key, value in grid.items()}, "calibration_grid_sha256": grid_hash},
        parameters={},
        metrics={"ngspice_calls": ngspice_calls, "successful": successful, "failed": len(rows) - successful},
        runtime_seconds=monotonic() - started,
        ngspice_executable=config.ngspice_config.executable,
        random_seed=None,
        run_id=run.run_id,
        resumed=False,
        resume_count=0,
        benchmark_config_hash=None,
        model_metadata=(
            None
            if model is None
            else (
                model.metadata()
                if isinstance(config.circuit_config, Sky130CommonSourceCircuitConfig)
                else {
                "model_path": str(model.require_library()),
                "model_library_sha256": model.library_sha256(),
                "model_name": model.model_name,
                "model_section": model.model_section,
                "corner": model.corner,
                "device_kind": model.device_kind,
                "provenance": model.provenance,
                }
            )
        ),
    )
    return CalibrationResult(run.run_id, run.path, csv_path, grid_hash, ngspice_calls, successful, len(rows) - successful)


def generate_sobol_candidates(
    config: ExperimentConfig,
    *,
    count: int = 256,
    scramble: bool = False,
    seed: int = 0,
) -> tuple[dict[str, float | int], ...]:
    """Return a fixed low-discrepancy design decoded through the search space."""
    if config.circuit_name != "sky130_differential_amplifier":
        raise ValueError("Sobol calibration is reserved for Task 5")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("Sobol count must be a positive integer")
    exponent = log2(count)
    if int(exponent) != exponent:
        raise ValueError("Sobol count must be a power of two")
    sampler = qmc.Sobol(
        d=len(config.search_space),
        scramble=scramble,
        seed=seed,
    )
    design = sampler.random_base2(int(exponent))
    candidates: list[dict[str, float | int]] = []
    for unit_row in design:
        candidate: dict[str, float | int] = {}
        for parameter, unit_value in zip(config.search_space, unit_row):
            assert parameter.low is not None and parameter.high is not None
            if parameter.log:
                value = exp(
                    log(float(parameter.low))
                    + float(unit_value)
                    * (log(float(parameter.high)) - log(float(parameter.low)))
                )
            else:
                value = float(parameter.low) + float(unit_value) * (
                    float(parameter.high) - float(parameter.low)
                )
            value = min(
                max(value, float(parameter.low)),
                float(parameter.high),
            )
            if parameter.parameter_type.value == "int":
                value = int(round(value))
            candidate[parameter.name] = value
        config.validate_parameters(candidate)
        candidates.append(candidate)
    return tuple(candidates)


def _candidate_design_hash(
    candidates: Sequence[Mapping[str, float | int]],
) -> str:
    encoded = json.dumps(
        list(candidates),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def run_differential_amplifier_calibration(
    config: ExperimentConfig,
    candidates: Sequence[Mapping[str, float | int]],
    *,
    published_csv: str | Path | None = None,
    scramble: bool = False,
    seed: int = 0,
) -> CalibrationResult:
    """Execute a pre-generated Task 5 design without optimizer feedback."""
    if (
        config.circuit_name != "sky130_differential_amplifier"
        or not isinstance(
            config.circuit_config, Sky130DifferentialAmplifierCircuitConfig
        )
    ):
        raise ValueError("Task 5 calibration requires differential-amplifier config")
    if not candidates:
        raise ValueError("Task 5 calibration candidates cannot be empty")
    run = prepare_research_run_directory(
        None, resume=False, default_root=config.output_dir
    )
    (run.path / "runs").mkdir(parents=True, exist_ok=True)
    write_experiment_config(config, run.path / "calibration_config.yaml")
    simulator = Sky130DifferentialAmplifierNgspiceSimulator(config)
    analyzer = Sky130DifferentialAmplifierAnalyzer(config)
    rows: list[dict[str, Any]] = []
    ngspice_calls = 0
    analysis_calls = 0
    started = monotonic()
    for iteration, raw_parameters in enumerate(candidates, start=1):
        parameters = dict(raw_parameters)
        config.validate_parameters(parameters)
        evidence = run.path / "runs" / f"calibration_{iteration:04d}"
        candidate_started = monotonic()
        called = 0

        def mark_call() -> None:
            nonlocal ngspice_calls, called
            ngspice_calls += 1
            called += 1

        status = "success"
        failure_type = None
        error_message = None
        returncode = None
        timed_out = False
        metrics: dict[str, float | None] = {}
        measurement_status = None
        bandwidth_status = None
        bandwidth_lower_bound_hz = None
        cmrr_status = None
        cmrr_lower_bound_db = None
        candidate_analysis_calls = 0
        try:
            simulation = simulator.evaluate(parameters, evidence, mark_call)
            candidate_analysis_calls = simulation.analysis_calls
            analysis_calls += candidate_analysis_calls
            outcome = analyzer.extract(simulation, parameters)
            metrics = outcome.metrics
            measurement_status = outcome.measurement_status
            bandwidth_status = outcome.bandwidth_status
            bandwidth_lower_bound_hz = outcome.bandwidth_lower_bound_hz
            cmrr_status = outcome.cmrr_status
            cmrr_lower_bound_db = outcome.cmrr_lower_bound_db
            if measurement_status != "complete":
                status = "measurement_incomplete"
                if "common-mode" in (outcome.message or ""):
                    failure_type = "invalid_common_mode_response"
                elif "differential" in (outcome.message or ""):
                    failure_type = "invalid_differential_response"
                else:
                    failure_type = "analysis_error"
                error_message = outcome.message
        except (CircuitPilotError, OSError, ValueError) as exc:
            status = (
                "simulation_failed"
                if isinstance(exc, SimulationError)
                else "evaluation_failed"
            )
            failure_type = type(exc).__name__
            error_message = str(exc)
            if isinstance(exc, SimulationError):
                returncode = exc.returncode
                timed_out = exc.timed_out
            evidence.mkdir(parents=True, exist_ok=True)
            (evidence / "calibration_error.txt").write_text(
                str(exc) + "\n", encoding="utf-8"
            )
        rows.append({
            "iteration": iteration,
            "parameters": parameters,
            "simulation_status": status,
            "measurement_status": measurement_status or "",
            "bandwidth_status": bandwidth_status or "",
            "bandwidth_lower_bound_hz": (
                "" if bandwidth_lower_bound_hz is None else bandwidth_lower_bound_hz
            ),
            "cmrr_status": cmrr_status or "",
            "cmrr_lower_bound_db": (
                "" if cmrr_lower_bound_db is None else cmrr_lower_bound_db
            ),
            "failure_type": failure_type or "",
            "error_message": error_message or "",
            "ngspice_return_code": "" if returncode is None else returncode,
            "timed_out": timed_out,
            "raw_metrics": metrics,
            "is_feasible_frozen_spec": None,
            "constraint_violation_frozen_spec": None,
            "simulation_time": monotonic() - candidate_started,
            "ngspice_called": called > 0,
            "ngspice_process_calls": called,
            "analysis_calls": candidate_analysis_calls,
            "evidence_directory": (Path("runs") / evidence.name).as_posix(),
        })
    if ngspice_calls != len(rows):
        raise ResearchExperimentError(
            "Task 5 calibration did not launch exactly one process per candidate"
        )
    csv_path = run.path / "differential_amplifier_calibration.csv"
    _write_rows(csv_path, rows)
    if published_csv is not None:
        destination = Path(published_csv).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(csv_path, destination)
    design_hash = _candidate_design_hash(candidates)
    successful = sum(row["simulation_status"] == "success" for row in rows)
    write_research_manifest(
        run.path,
        workflow="calibration",
        circuit_type=config.circuit_name,
        configuration={
            **config.to_dict(),
            "calibration_design": {
                "kind": "sobol",
                "count": len(candidates),
                "scramble": scramble,
                "seed_metadata": seed,
                "candidate_design_sha256": design_hash,
            },
        },
        parameters={},
        metrics={
            "candidate_evaluations": len(rows),
            "ngspice_process_calls": ngspice_calls,
            "analysis_calls": analysis_calls,
            "successful": successful,
            "failed": len(rows) - successful,
        },
        runtime_seconds=monotonic() - started,
        ngspice_executable=config.ngspice_config.executable,
        random_seed=None,
        run_id=run.run_id,
        resumed=False,
        resume_count=0,
        benchmark_config_hash=None,
        model_metadata=config.circuit_config.model.metadata(),
    )
    return CalibrationResult(
        run.run_id,
        run.path,
        csv_path,
        design_hash,
        ngspice_calls,
        successful,
        len(rows) - successful,
        analysis_calls,
    )


def annotate_calibration_with_frozen_spec(
    calibration_csv: str | Path, frozen_config: ExperimentConfig
) -> tuple[int, int]:
    """Annotate existing raw rows without launching or synthesizing simulations."""
    if frozen_config.circuit_name not in {
        "common_source",
        "sky130_common_source",
        "sky130_differential_amplifier",
    }:
        raise ValueError("unsupported frozen calibration specification")
    source = Path(calibration_csv).resolve()
    try:
        with source.open("r", encoding="utf-8", newline="") as stream:
            raw_rows = list(csv.DictReader(stream))
    except OSError as exc:
        raise ResearchExperimentError(f"cannot read calibration CSV '{source}': {exc}") from exc
    evaluator = ObjectiveEvaluator(frozen_config)
    rows: list[dict[str, Any]] = []
    feasible = 0
    successful = 0
    for raw in raw_rows:
        try:
            parameters = json.loads(raw["parameters"])
            metrics = json.loads(raw["raw_metrics"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ResearchExperimentError(f"invalid calibration row: {exc}") from exc
        is_feasible: bool | None = None
        violation: float | None = None
        if raw["simulation_status"] == "success":
            successful += 1
            evaluation = evaluator.evaluate(
                metrics,
                bandwidth_status=raw.get("bandwidth_status") or None,
                bandwidth_lower_bound_hz=(
                    None
                    if raw.get("bandwidth_lower_bound_hz", "") == ""
                    else float(raw["bandwidth_lower_bound_hz"])
                ),
                cmrr_status=raw.get("cmrr_status") or None,
                cmrr_lower_bound_db=(
                    None
                    if raw.get("cmrr_lower_bound_db", "") == ""
                    else float(raw["cmrr_lower_bound_db"])
                ),
            )
            is_feasible = evaluation.is_feasible
            violation = evaluation.constraint_violation
            feasible += int(is_feasible)
        rows.append(
            {
                **raw,
                "parameters": parameters,
                "raw_metrics": metrics,
                "timed_out": raw["timed_out"].lower() == "true",
                "ngspice_called": raw["ngspice_called"].lower() == "true",
                "ngspice_process_calls": int(
                    raw.get("ngspice_process_calls")
                    or int(raw["ngspice_called"].lower() == "true")
                ),
                "analysis_calls": int(raw.get("analysis_calls") or 0),
                "cmrr_status": raw.get("cmrr_status", ""),
                "cmrr_lower_bound_db": raw.get("cmrr_lower_bound_db", ""),
                "is_feasible_frozen_spec": is_feasible,
                "constraint_violation_frozen_spec": violation,
            }
        )
    _write_rows(source, rows)
    return feasible, successful


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic transistor calibration")
    parser.add_argument("--config", required=True)
    parser.add_argument("--grid")
    parser.add_argument("--sobol-count", type=int, default=256)
    parser.add_argument("--publish-csv")
    args = parser.parse_args(argv)
    config = load_experiment_config(args.config)
    if config.circuit_name == "sky130_differential_amplifier":
        candidates = generate_sobol_candidates(
            config, count=args.sobol_count, scramble=False, seed=0
        )
        result = run_differential_amplifier_calibration(
            config,
            candidates,
            published_csv=args.publish_csv,
            scramble=False,
            seed=0,
        )
    else:
        if args.grid is None:
            parser.error("--grid is required for common-source calibration")
        grid = load_calibration_grid(args.grid, config)
        result = run_common_source_calibration(
            config, grid, published_csv=args.publish_csv
        )
    print(f"Run ID: {result.run_id}")
    print(f"ngspice calls: {result.ngspice_calls}")
    print(f"Succeeded: {result.successful}")
    print(f"Failed: {result.failed}")
    print(f"Output directory: {result.output_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
