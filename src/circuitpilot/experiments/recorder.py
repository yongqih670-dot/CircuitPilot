"""Uniform CSV and SQLite persistence for every candidate evaluation."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from math import isfinite
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from circuitpilot.exceptions import ResearchExperimentError


EVALUATION_COLUMNS = (
    "experiment_id",
    "run_id",
    "circuit",
    "method",
    "optimizer_phase",
    "seed",
    "iteration",
    "parameters",
    "simulation_status",
    "failure_type",
    "error_message",
    "ngspice_return_code",
    "timed_out",
    "raw_metrics",
    "objective_value",
    "constraint_violation",
    "is_feasible",
    "simulation_time",
    "total_elapsed_time",
    "timestamp",
    "run_directory",
    "ngspice_called",
    "benchmark_config_hash",
    "experiment_phase",
    "event_observed",
    "evaluation_time",
)


def _finite_optional(value: float | None, context: str) -> float | None:
    """Validate an optional finite numeric record field."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{context} must be numeric or null")
    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError(f"{context} must be finite or null")
    return numeric


def _numeric_mapping(value: Mapping[str, Any], context: str) -> dict[str, float]:
    """Return a finite string-keyed physical-metric mapping."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{context} must be a mapping")
    normalized: dict[str, float] = {}
    for name, item in value.items():
        if not isinstance(name, str) or not name:
            raise ValueError(f"{context} keys must be non-empty strings")
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{context}.{name} must be numeric")
        numeric = float(item)
        if not isfinite(numeric):
            raise ValueError(f"{context}.{name} must be finite")
        normalized[name] = numeric
    return normalized


def _parameter_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate JSON-scalar candidate parameters, including categories."""
    if not isinstance(value, Mapping):
        raise ValueError("parameters must be a mapping")
    normalized: dict[str, Any] = {}
    for name, item in value.items():
        if not isinstance(name, str) or not name:
            raise ValueError("parameter names must be non-empty strings")
        if not isinstance(item, (str, int, float, bool)):
            raise ValueError(f"parameters.{name} must be a JSON scalar")
        if isinstance(item, float) and not isfinite(item):
            raise ValueError(f"parameters.{name} must be finite")
        normalized[name] = item
    return normalized


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    """Method-neutral record for one candidate slot."""

    experiment_id: str
    run_id: str
    circuit: str
    method: str
    seed: int
    iteration: int
    parameters: dict[str, Any]
    simulation_status: str
    failure_type: str | None
    raw_metrics: dict[str, float]
    objective_value: float | None
    constraint_violation: float | None
    simulation_time: float
    total_elapsed_time: float
    timestamp: str
    run_directory: str
    ngspice_called: bool
    optimizer_phase: str = "search"
    is_feasible: bool = False
    error_message: str | None = None
    ngspice_return_code: int | None = None
    timed_out: bool = False
    benchmark_config_hash: str | None = None
    experiment_phase: str = "baseline"
    event_observed: bool = False
    evaluation_time: int | None = None

    def __post_init__(self) -> None:
        """Reject malformed, non-finite, or internally inconsistent records."""
        for name in ("experiment_id", "run_id", "circuit", "method"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a non-empty string")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if (
            isinstance(self.iteration, bool)
            or not isinstance(self.iteration, int)
            or self.iteration <= 0
        ):
            raise ValueError("iteration must be a positive integer")
        _parameter_mapping(self.parameters)
        if not isinstance(self.optimizer_phase, str) or not self.optimizer_phase:
            raise ValueError("optimizer_phase must be non-empty")
        if not isinstance(self.simulation_status, str) or not self.simulation_status:
            raise ValueError("simulation_status must be non-empty")
        if self.failure_type is not None and (
            not isinstance(self.failure_type, str) or not self.failure_type
        ):
            raise ValueError("failure_type must be a non-empty string or null")
        if self.error_message is not None and not isinstance(self.error_message, str):
            raise ValueError("error_message must be a string or null")
        if self.ngspice_return_code is not None and (
            isinstance(self.ngspice_return_code, bool)
            or not isinstance(self.ngspice_return_code, int)
        ):
            raise ValueError("ngspice_return_code must be an integer or null")
        if not isinstance(self.timed_out, bool):
            raise ValueError("timed_out must be a boolean")
        if self.benchmark_config_hash is not None and (
            not isinstance(self.benchmark_config_hash, str)
            or len(self.benchmark_config_hash) != 64
        ):
            raise ValueError("benchmark_config_hash must be a SHA-256 string or null")
        if self.experiment_phase not in {"baseline", "smoke", "calibration"}:
            raise ValueError("experiment_phase must be baseline, smoke, or calibration")
        if not isinstance(self.event_observed, bool):
            raise ValueError("event_observed must be a boolean")
        if self.evaluation_time is not None and (
            isinstance(self.evaluation_time, bool)
            or not isinstance(self.evaluation_time, int)
            or self.evaluation_time <= 0
        ):
            raise ValueError("evaluation_time must be a positive integer or null")
        _numeric_mapping(self.raw_metrics, "raw_metrics")
        _finite_optional(self.objective_value, "objective_value")
        violation = _finite_optional(
            self.constraint_violation, "constraint_violation"
        )
        if violation is not None and violation < 0:
            raise ValueError("constraint_violation must be non-negative")
        for name in ("simulation_time", "total_elapsed_time"):
            value = _finite_optional(getattr(self, name), name)
            if value is None or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not isinstance(self.timestamp, str) or not self.timestamp:
            raise ValueError("timestamp must be non-empty")
        if not isinstance(self.run_directory, str) or not self.run_directory:
            raise ValueError("run_directory must be non-empty")
        if not isinstance(self.ngspice_called, bool):
            raise ValueError("ngspice_called must be a boolean")
        if not isinstance(self.is_feasible, bool):
            raise ValueError("is_feasible must be a boolean")
        if self.simulation_status == "success":
            if self.failure_type is not None:
                raise ValueError("successful records cannot have failure_type")
            if self.objective_value is None or self.constraint_violation is None:
                raise ValueError("successful records require objective and constraints")
            if not self.raw_metrics:
                raise ValueError("successful records require raw_metrics")
            if not self.ngspice_called:
                raise ValueError("successful records require a real ngspice call")
            if self.error_message is not None or self.timed_out:
                raise ValueError("successful records cannot contain failure evidence")
        elif self.objective_value is not None or self.constraint_violation is not None:
            raise ValueError("failed records cannot contain optimizer-facing values")
        elif self.is_feasible:
            raise ValueError("failed records cannot be feasible")

    @classmethod
    def now(
        cls,
        *,
        experiment_id: str,
        run_id: str,
        circuit: str,
        method: str,
        seed: int,
        iteration: int,
        parameters: Mapping[str, Any],
        simulation_status: str,
        failure_type: str | None,
        raw_metrics: Mapping[str, float],
        objective_value: float | None,
        constraint_violation: float | None,
        simulation_time: float,
        total_elapsed_time: float,
        run_directory: str,
        ngspice_called: bool,
        optimizer_phase: str = "search",
        is_feasible: bool = False,
        error_message: str | None = None,
        ngspice_return_code: int | None = None,
        timed_out: bool = False,
        benchmark_config_hash: str | None = None,
        experiment_phase: str = "baseline",
        event_observed: bool = False,
        evaluation_time: int | None = None,
    ) -> "EvaluationRecord":
        """Construct a record with a UTC timestamp."""
        return cls(
            experiment_id=experiment_id,
            run_id=run_id,
            circuit=circuit,
            method=method,
            seed=seed,
            iteration=iteration,
            parameters=dict(parameters),
            simulation_status=simulation_status,
            failure_type=failure_type,
            raw_metrics=dict(raw_metrics),
            objective_value=objective_value,
            constraint_violation=constraint_violation,
            simulation_time=simulation_time,
            total_elapsed_time=total_elapsed_time,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
            run_directory=run_directory,
            ngspice_called=ngspice_called,
            optimizer_phase=optimizer_phase,
            is_feasible=is_feasible,
            error_message=error_message,
            ngspice_return_code=ngspice_return_code,
            timed_out=timed_out,
            benchmark_config_hash=benchmark_config_hash,
            experiment_phase=experiment_phase,
            event_observed=event_observed,
            evaluation_time=evaluation_time,
        )


class EvaluationRecorder:
    """Persist identical evaluation rows to CSV and SQLite after every tell."""

    SCHEMA_VERSION = 3

    def __init__(self, output_directory: str | Path) -> None:
        """Initialize the per-run CSV and SQLite stores."""
        self.output_directory = Path(output_directory).resolve()
        self.csv_path = self.output_directory / "evaluations.csv"
        self.database_path = self.output_directory / "evaluations.sqlite3"
        try:
            self.output_directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ResearchExperimentError(
                f"failed to create evaluation output '{self.output_directory}': {exc}"
            ) from exc
        self._initialize_database()
        self._write_csv(self.records())

    def _connect(self) -> sqlite3.Connection:
        """Open a configured SQLite connection."""
        try:
            connection = sqlite3.connect(self.database_path, timeout=10.0)
        except sqlite3.Error as exc:
            raise ResearchExperimentError(
                f"failed to open evaluation database '{self.database_path}': {exc}"
            ) from exc
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self) -> None:
        """Create the method-neutral evaluation table and version marker."""
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS research_evaluations (
                        run_id TEXT NOT NULL,
                        iteration INTEGER NOT NULL,
                        experiment_id TEXT NOT NULL,
                        circuit TEXT NOT NULL,
                        method TEXT NOT NULL,
                        optimizer_phase TEXT NOT NULL DEFAULT 'search',
                        seed INTEGER NOT NULL,
                        parameters_json TEXT NOT NULL,
                        simulation_status TEXT NOT NULL,
                        failure_type TEXT,
                        error_message TEXT,
                        ngspice_return_code INTEGER,
                        timed_out INTEGER NOT NULL DEFAULT 0,
                        raw_metrics_json TEXT NOT NULL,
                        objective_value REAL,
                        constraint_violation REAL,
                        is_feasible INTEGER NOT NULL DEFAULT 0,
                        simulation_time REAL NOT NULL,
                        total_elapsed_time REAL NOT NULL,
                        timestamp TEXT NOT NULL,
                        run_directory TEXT NOT NULL,
                        ngspice_called INTEGER NOT NULL,
                        benchmark_config_hash TEXT,
                        experiment_phase TEXT NOT NULL DEFAULT 'baseline',
                        event_observed INTEGER NOT NULL DEFAULT 0,
                        evaluation_time INTEGER,
                        PRIMARY KEY (run_id, iteration)
                    );
                    """
                )
                version = connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1, 2, self.SCHEMA_VERSION):
                    raise ResearchExperimentError(
                        f"unsupported evaluation database schema {version}"
                    )
                columns = {row[1] for row in connection.execute("PRAGMA table_info(research_evaluations)")}
                if "optimizer_phase" not in columns:
                    connection.execute("ALTER TABLE research_evaluations ADD COLUMN optimizer_phase TEXT NOT NULL DEFAULT 'search'")
                if "is_feasible" not in columns:
                    connection.execute("ALTER TABLE research_evaluations ADD COLUMN is_feasible INTEGER NOT NULL DEFAULT 0")
                migrations = {
                    "error_message": "TEXT",
                    "ngspice_return_code": "INTEGER",
                    "timed_out": "INTEGER NOT NULL DEFAULT 0",
                    "benchmark_config_hash": "TEXT",
                    "experiment_phase": "TEXT NOT NULL DEFAULT 'baseline'",
                    "event_observed": "INTEGER NOT NULL DEFAULT 0",
                    "evaluation_time": "INTEGER",
                }
                for name, declaration in migrations.items():
                    if name not in columns:
                        connection.execute(
                            f"ALTER TABLE research_evaluations ADD COLUMN {name} {declaration}"
                        )
                connection.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
        except sqlite3.Error as exc:
            raise ResearchExperimentError(
                f"failed to initialize evaluation database: {exc}"
            ) from exc

    def save(self, record: EvaluationRecord) -> None:
        """Insert one immutable row, then regenerate canonical CSV from SQLite."""
        parameters_json = json.dumps(
            record.parameters, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        metrics_json = json.dumps(
            record.raw_metrics, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO research_evaluations (
                        run_id, iteration, experiment_id, circuit, method, optimizer_phase, seed,
                        parameters_json, simulation_status, failure_type,
                        error_message, ngspice_return_code, timed_out,
                        raw_metrics_json, objective_value, constraint_violation, is_feasible,
                        simulation_time, total_elapsed_time, timestamp,
                        run_directory, ngspice_called, benchmark_config_hash,
                        experiment_phase, event_observed, evaluation_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.run_id,
                        record.iteration,
                        record.experiment_id,
                        record.circuit,
                        record.method,
                        record.optimizer_phase,
                        record.seed,
                        parameters_json,
                        record.simulation_status,
                        record.failure_type,
                        record.error_message,
                        record.ngspice_return_code,
                        int(record.timed_out),
                        metrics_json,
                        record.objective_value,
                        record.constraint_violation,
                        int(record.is_feasible),
                        record.simulation_time,
                        record.total_elapsed_time,
                        record.timestamp,
                        record.run_directory,
                        int(record.ngspice_called),
                        record.benchmark_config_hash,
                        record.experiment_phase,
                        int(record.event_observed),
                        record.evaluation_time,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ResearchExperimentError(
                f"evaluation {record.iteration} is already recorded for {record.run_id}"
            ) from exc
        except sqlite3.Error as exc:
            raise ResearchExperimentError(f"failed to save evaluation: {exc}") from exc
        self._write_csv(self.records())

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> EvaluationRecord:
        """Convert one SQLite row back to the public record type."""
        try:
            parameters = json.loads(row["parameters_json"])
            raw_metrics = json.loads(row["raw_metrics_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ResearchExperimentError(
                f"evaluation row {row['iteration']} contains invalid JSON"
            ) from exc
        return EvaluationRecord(
            experiment_id=row["experiment_id"],
            run_id=row["run_id"],
            circuit=row["circuit"],
            method=row["method"],
            optimizer_phase=row["optimizer_phase"],
            seed=row["seed"],
            iteration=row["iteration"],
            parameters=parameters,
            simulation_status=row["simulation_status"],
            failure_type=row["failure_type"],
            error_message=row["error_message"],
            ngspice_return_code=row["ngspice_return_code"],
            timed_out=bool(row["timed_out"]),
            raw_metrics=raw_metrics,
            objective_value=row["objective_value"],
            constraint_violation=row["constraint_violation"],
            is_feasible=bool(row["is_feasible"]),
            simulation_time=row["simulation_time"],
            total_elapsed_time=row["total_elapsed_time"],
            timestamp=row["timestamp"],
            run_directory=row["run_directory"],
            ngspice_called=bool(row["ngspice_called"]),
            benchmark_config_hash=row["benchmark_config_hash"],
            experiment_phase=row["experiment_phase"],
            event_observed=bool(row["event_observed"]),
            evaluation_time=row["evaluation_time"],
        )

    def records(self) -> tuple[EvaluationRecord, ...]:
        """Load all rows in deterministic iteration order."""
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM research_evaluations ORDER BY iteration"
                ).fetchall()
        except sqlite3.Error as exc:
            raise ResearchExperimentError(f"failed to load evaluations: {exc}") from exc
        return tuple(self._row_to_record(row) for row in rows)

    def _write_csv(self, records: tuple[EvaluationRecord, ...]) -> None:
        """Atomically mirror all SQLite rows to the common CSV schema."""
        temporary = self.csv_path.with_name(f".{self.csv_path.name}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=EVALUATION_COLUMNS)
                writer.writeheader()
                for record in records:
                    writer.writerow(
                        {
                            "experiment_id": record.experiment_id,
                            "run_id": record.run_id,
                            "circuit": record.circuit,
                            "method": record.method,
                            "optimizer_phase": record.optimizer_phase,
                            "seed": record.seed,
                            "iteration": record.iteration,
                            "parameters": json.dumps(
                                record.parameters,
                                sort_keys=True,
                                separators=(",", ":"),
                                allow_nan=False,
                            ),
                            "simulation_status": record.simulation_status,
                            "failure_type": record.failure_type or "",
                            "error_message": record.error_message or "",
                            "ngspice_return_code": (
                                "" if record.ngspice_return_code is None else record.ngspice_return_code
                            ),
                            "timed_out": str(record.timed_out).lower(),
                            "raw_metrics": json.dumps(
                                record.raw_metrics,
                                sort_keys=True,
                                separators=(",", ":"),
                                allow_nan=False,
                            ),
                            "objective_value": (
                                ""
                                if record.objective_value is None
                                else f"{record.objective_value:.17g}"
                            ),
                            "constraint_violation": (
                                ""
                                if record.constraint_violation is None
                                else f"{record.constraint_violation:.17g}"
                            ),
                            "is_feasible": str(record.is_feasible).lower(),
                            "simulation_time": f"{record.simulation_time:.17g}",
                            "total_elapsed_time": f"{record.total_elapsed_time:.17g}",
                            "timestamp": record.timestamp,
                            "run_directory": record.run_directory,
                            "ngspice_called": str(record.ngspice_called).lower(),
                            "benchmark_config_hash": record.benchmark_config_hash or "",
                            "experiment_phase": record.experiment_phase,
                            "event_observed": str(record.event_observed).lower(),
                            "evaluation_time": (
                                "" if record.evaluation_time is None else record.evaluation_time
                            ),
                        }
                    )
            temporary.replace(self.csv_path)
        except (OSError, TypeError, ValueError) as exc:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ResearchExperimentError(
                f"failed to write evaluations CSV '{self.csv_path}': {exc}"
            ) from exc
