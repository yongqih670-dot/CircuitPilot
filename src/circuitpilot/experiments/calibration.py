"""Deterministic, non-optimizer calibration for transistor benchmarks."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
import shutil
from time import monotonic
from typing import Any, Mapping, Sequence

import yaml

from circuitpilot.common_source import analyze_common_source
from circuitpilot.exceptions import CircuitPilotError, ConfigError, ResearchExperimentError, SimulationError
from circuitpilot.experiments.config import ExperimentConfig, load_experiment_config, write_experiment_config
from circuitpilot.experiments.objectives import ObjectiveEvaluator
from circuitpilot.experiments.simulation import CommonSourceNgspiceSimulator
from circuitpilot.research_artifacts import write_research_manifest
from circuitpilot.run_directory import prepare_research_run_directory


CALIBRATION_COLUMNS = (
    "iteration",
    "parameters",
    "simulation_status",
    "failure_type",
    "error_message",
    "ngspice_return_code",
    "timed_out",
    "raw_metrics",
    "is_feasible_frozen_spec",
    "constraint_violation_frozen_spec",
    "simulation_time",
    "ngspice_called",
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
    if config.circuit_name != "common_source":
        raise ValueError("calibration supports only common_source")
    run = prepare_research_run_directory(None, resume=False, default_root=config.output_dir)
    (run.path / "runs").mkdir(parents=True, exist_ok=True)
    write_experiment_config(config, run.path / "calibration_config.yaml")
    ordered_names = tuple(parameter.name for parameter in config.search_space)
    rows: list[dict[str, Any]] = []
    ngspice_calls = 0
    simulator = CommonSourceNgspiceSimulator(config)
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
        metrics: dict[str, float] = {}
        try:
            simulation = simulator.evaluate(parameters, evidence, mark_call)
            if simulation.operating_point is None:
                raise ResearchExperimentError("calibration simulation has no operating point")
            metrics = analyze_common_source(
                simulation.response, simulation.operating_point
            ).to_dict()
            metrics.update(simulation.operating_point.device_quantities)
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
            else {
                "model_path": str(model.require_library()),
                "model_library_sha256": model.library_sha256(),
                "model_name": model.model_name,
                "model_section": model.model_section,
                "corner": model.corner,
                "device_kind": model.device_kind,
                "provenance": model.provenance,
            }
        ),
    )
    return CalibrationResult(run.run_id, run.path, csv_path, grid_hash, ngspice_calls, successful, len(rows) - successful)


def annotate_calibration_with_frozen_spec(
    calibration_csv: str | Path, frozen_config: ExperimentConfig
) -> tuple[int, int]:
    """Annotate existing raw rows without launching or synthesizing simulations."""
    if frozen_config.circuit_name != "common_source":
        raise ValueError("frozen calibration specification must be common_source")
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
            evaluation = evaluator.evaluate(metrics)
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
                "is_feasible_frozen_spec": is_feasible,
                "constraint_violation_frozen_spec": violation,
            }
        )
    _write_rows(source, rows)
    return feasible, successful


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic common-source calibration")
    parser.add_argument("--config", required=True)
    parser.add_argument("--grid", required=True)
    parser.add_argument("--publish-csv")
    args = parser.parse_args(argv)
    config = load_experiment_config(args.config)
    grid = load_calibration_grid(args.grid, config)
    result = run_common_source_calibration(config, grid, published_csv=args.publish_csv)
    print(f"Run ID: {result.run_id}")
    print(f"ngspice calls: {result.ngspice_calls}")
    print(f"Succeeded: {result.successful}")
    print(f"Failed: {result.failed}")
    print(f"Output directory: {result.output_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
