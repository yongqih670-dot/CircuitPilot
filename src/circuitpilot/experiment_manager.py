"""SQLite-backed experiment creation, history, ranking, and comparison."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from math import isfinite
from pathlib import Path
import sqlite3
from typing import Any, Mapping, Sequence

from circuitpilot.circuit_config import CircuitType
from circuitpilot.exceptions import ExperimentError


SCHEMA_VERSION = 1
DEFAULT_DATABASE_PATH = Path("experiments") / "circuitpilot.sqlite3"


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    """One immutable experiment snapshot loaded from SQLite."""

    experiment_id: int
    name: str
    circuit_type: str
    parameters: dict[str, Any]
    simulation_time_seconds: float
    metrics: dict[str, float]
    created_at: str


@dataclass(frozen=True, slots=True)
class ExperimentComparison:
    """One metric value and its difference from a historical baseline."""

    experiment_id: int
    experiment_name: str
    metric_name: str
    metric_value: float
    difference_from_baseline: float
    relative_difference_from_baseline: float | None


def _serialize_mapping(value: Mapping[str, Any], context: str) -> str:
    """Serialize JSON deterministically and reject NaN or unsupported values."""
    if not isinstance(value, Mapping):
        raise ExperimentError(f"{context} must be a mapping")
    if not all(isinstance(key, str) and key.strip() for key in value):
        raise ExperimentError(f"{context} keys must be non-empty strings")
    try:
        return json.dumps(
            dict(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise ExperimentError(f"{context} must contain JSON-compatible values") from exc


def _validate_metrics(metrics: Mapping[str, float]) -> dict[str, float]:
    """Return numeric finite metrics suitable for ranking and comparison."""
    if not metrics:
        raise ExperimentError("metrics must contain at least one performance value")
    normalized: dict[str, float] = {}
    for name, value in metrics.items():
        if not isinstance(name, str) or not name.strip():
            raise ExperimentError("metric names must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ExperimentError(f"metric '{name}' must be numeric")
        numeric_value = float(value)
        if not isfinite(numeric_value):
            raise ExperimentError(f"metric '{name}' must be finite")
        normalized[name] = numeric_value
    return normalized


class ExperimentRepository:
    """Manage CircuitPilot experiment history in one SQLite database."""

    def __init__(self, database_path: str | Path = DEFAULT_DATABASE_PATH) -> None:
        """Create the database parent directory and initialize its schema."""
        self.database_path = Path(database_path).resolve()
        try:
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ExperimentError(
                f"failed to create database directory '{self.database_path.parent}': {exc}"
            ) from exc
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        """Open a configured SQLite connection with named result columns."""
        try:
            connection = sqlite3.connect(self.database_path, timeout=10.0)
        except sqlite3.Error as exc:
            raise ExperimentError(
                f"failed to open experiment database '{self.database_path}': {exc}"
            ) from exc
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_schema(self) -> None:
        """Create the versioned experiment schema and lookup index."""
        try:
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS experiments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL CHECK(length(trim(name)) > 0),
                        circuit_type TEXT NOT NULL,
                        parameters_json TEXT NOT NULL,
                        simulation_time_seconds REAL NOT NULL
                            CHECK(simulation_time_seconds >= 0),
                        metrics_json TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_experiments_type_created
                        ON experiments(circuit_type, created_at DESC, id DESC);
                    """
                )
                current_version = connection.execute("PRAGMA user_version").fetchone()[0]
                if current_version not in (0, SCHEMA_VERSION):
                    raise ExperimentError(
                        f"unsupported experiment schema version {current_version}"
                    )
                connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        except sqlite3.Error as exc:
            raise ExperimentError(f"failed to initialize experiment database: {exc}") from exc

    @staticmethod
    def _normalize_circuit_type(circuit_type: str | CircuitType) -> str:
        """Validate a currently supported circuit type."""
        raw_value = circuit_type.value if isinstance(circuit_type, CircuitType) else circuit_type
        if not isinstance(raw_value, str):
            raise ExperimentError("circuit_type must be a string")
        try:
            return CircuitType(raw_value).value
        except ValueError:
            supported = ", ".join(member.value for member in CircuitType)
            raise ExperimentError(
                f"unsupported circuit_type '{raw_value}'; expected one of: {supported}"
            ) from None

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> ExperimentRecord:
        """Convert one SQLite row and its JSON snapshots to a record."""
        try:
            parameters = json.loads(row["parameters_json"])
            metrics = json.loads(row["metrics_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ExperimentError(
                f"experiment {row['id']} contains invalid JSON data"
            ) from exc
        return ExperimentRecord(
            experiment_id=row["id"],
            name=row["name"],
            circuit_type=row["circuit_type"],
            parameters=parameters,
            simulation_time_seconds=row["simulation_time_seconds"],
            metrics=metrics,
            created_at=row["created_at"],
        )

    def create_experiment(
        self,
        *,
        name: str,
        circuit_type: str | CircuitType,
        parameters: Mapping[str, Any],
        simulation_time_seconds: float,
        metrics: Mapping[str, float],
        created_at: str | None = None,
    ) -> ExperimentRecord:
        """Validate and persist one experiment snapshot atomically."""
        if not isinstance(name, str) or not name.strip():
            raise ExperimentError("experiment name must be a non-empty string")
        normalized_name = name.strip()
        if len(normalized_name) > 200:
            raise ExperimentError("experiment name must not exceed 200 characters")
        normalized_type = self._normalize_circuit_type(circuit_type)
        parameters_json = _serialize_mapping(parameters, "parameters")
        normalized_metrics = _validate_metrics(metrics)
        metrics_json = _serialize_mapping(normalized_metrics, "metrics")
        if (
            isinstance(simulation_time_seconds, bool)
            or not isinstance(simulation_time_seconds, (int, float))
            or not isfinite(float(simulation_time_seconds))
            or simulation_time_seconds < 0
        ):
            raise ExperimentError("simulation_time_seconds must be finite and non-negative")
        timestamp = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not isinstance(timestamp, str) or not timestamp.strip():
            raise ExperimentError("created_at must be a non-empty ISO timestamp")

        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO experiments (
                        name, circuit_type, parameters_json,
                        simulation_time_seconds, metrics_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized_name,
                        normalized_type,
                        parameters_json,
                        float(simulation_time_seconds),
                        metrics_json,
                        timestamp,
                    ),
                )
                experiment_id = cursor.lastrowid
        except sqlite3.Error as exc:
            raise ExperimentError(f"failed to create experiment: {exc}") from exc
        if experiment_id is None:
            raise ExperimentError("SQLite did not return an experiment id")
        return self.get_experiment(experiment_id)

    def get_experiment(self, experiment_id: int) -> ExperimentRecord:
        """Load one experiment by primary key."""
        if isinstance(experiment_id, bool) or not isinstance(experiment_id, int):
            raise ExperimentError("experiment_id must be an integer")
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM experiments WHERE id = ?", (experiment_id,)
                ).fetchone()
        except sqlite3.Error as exc:
            raise ExperimentError(f"failed to load experiment: {exc}") from exc
        if row is None:
            raise ExperimentError(f"experiment {experiment_id} does not exist")
        return self._row_to_record(row)

    def list_experiments(
        self,
        *,
        circuit_type: str | CircuitType | None = None,
        limit: int | None = None,
    ) -> tuple[ExperimentRecord, ...]:
        """List newest experiments, optionally filtered by circuit type."""
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0
        ):
            raise ExperimentError("limit must be a positive integer")
        parameters: list[Any] = []
        query = "SELECT * FROM experiments"
        if circuit_type is not None:
            query += " WHERE circuit_type = ?"
            parameters.append(self._normalize_circuit_type(circuit_type))
        query += " ORDER BY created_at DESC, id DESC"
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)
        try:
            with self._connect() as connection:
                rows = connection.execute(query, parameters).fetchall()
        except sqlite3.Error as exc:
            raise ExperimentError(f"failed to list experiments: {exc}") from exc
        return tuple(self._row_to_record(row) for row in rows)

    def show_best_result(
        self,
        metric_name: str,
        *,
        circuit_type: str | CircuitType | None = None,
        minimize: bool = True,
    ) -> ExperimentRecord:
        """Return the experiment with the best numeric value for one metric."""
        if not isinstance(metric_name, str) or not metric_name.strip():
            raise ExperimentError("metric_name must be a non-empty string")
        candidates = [
            record
            for record in self.list_experiments(circuit_type=circuit_type)
            if metric_name in record.metrics
        ]
        if not candidates:
            raise ExperimentError(f"no experiments contain metric '{metric_name}'")
        if minimize:
            return min(
                candidates,
                key=lambda record: (
                    record.metrics[metric_name],
                    record.simulation_time_seconds,
                    record.experiment_id,
                ),
            )
        return max(
            candidates,
            key=lambda record: (
                record.metrics[metric_name],
                -record.simulation_time_seconds,
                -record.experiment_id,
            ),
        )

    def compare_experiments(
        self,
        metric_name: str,
        *,
        experiment_ids: Sequence[int] | None = None,
        circuit_type: str | CircuitType | None = None,
    ) -> tuple[ExperimentComparison, ...]:
        """Compare a metric against the first experiment as historical baseline."""
        if not isinstance(metric_name, str) or not metric_name.strip():
            raise ExperimentError("metric_name must be a non-empty string")
        if experiment_ids is not None:
            if len(experiment_ids) < 2:
                raise ExperimentError("comparison requires at least two experiment ids")
            records = tuple(self.get_experiment(identifier) for identifier in experiment_ids)
        else:
            history = self.list_experiments(circuit_type=circuit_type)
            records = tuple(reversed(history))
            if len(records) < 2:
                raise ExperimentError("comparison requires at least two experiments")

        for record in records:
            if metric_name not in record.metrics:
                raise ExperimentError(
                    f"experiment {record.experiment_id} does not contain metric "
                    f"'{metric_name}'"
                )
        baseline = records[0].metrics[metric_name]
        comparisons: list[ExperimentComparison] = []
        for record in records:
            value = record.metrics[metric_name]
            difference = value - baseline
            relative_difference = None if baseline == 0 else difference / abs(baseline)
            comparisons.append(
                ExperimentComparison(
                    experiment_id=record.experiment_id,
                    experiment_name=record.name,
                    metric_name=metric_name,
                    metric_value=value,
                    difference_from_baseline=difference,
                    relative_difference_from_baseline=relative_difference,
                )
            )
        return tuple(comparisons)

