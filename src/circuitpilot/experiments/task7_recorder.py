"""Transactional candidate-level SQLite and CSV evidence for Research Task 7."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from math import isfinite
from pathlib import Path
import sqlite3
from time import sleep
from typing import Any, Mapping

from circuitpilot.exceptions import ResearchExperimentError


TASK7_COLUMNS = (
    "experiment_id",
    "run_id",
    "experiment_design",
    "method",
    "optimizer_phase",
    "seed",
    "iteration",
    "parameters",
    "simulation_status",
    "metrics",
    "ugf_status",
    "phase_margin_status",
    "ugf_crossing_count",
    "positive_slew_status",
    "negative_slew_status",
    "operating_region_valid",
    "operating_region_mask",
    "operating_region_types",
    "device_status",
    "device_quantities",
    "analysis_errors",
    "objective_value",
    "constraint_violation",
    "constraint_components",
    "is_feasible",
    "event_observed",
    "candidate_evaluations",
    "ngspice_process_calls",
    "op_calls",
    "ac_calls",
    "transient_calls",
    "high_fidelity_analysis_calls",
    "screening_calls",
    "op_runtime_seconds",
    "ac_runtime_seconds",
    "transient_runtime_seconds",
    "wall_clock_seconds",
    "total_elapsed_time",
    "candidate_evaluations_cumulative",
    "ngspice_process_calls_cumulative",
    "op_calls_cumulative",
    "ac_calls_cumulative",
    "transient_calls_cumulative",
    "high_fidelity_analysis_calls_cumulative",
    "screening_calls_cumulative",
    "timestamp",
    "run_directory",
    "task7_benchmark_hash",
    "task7_search_space_hash",
    "task7_protocol_family_hash",
)
JSON_FIELDS = {
    "parameters",
    "metrics",
    "operating_region_types",
    "device_status",
    "device_quantities",
    "analysis_errors",
    "constraint_components",
}


@dataclass(frozen=True, slots=True)
class Task7EvaluationRecord:
    """One immutable Full-evaluation row."""

    experiment_id: str
    run_id: str
    experiment_design: str
    method: str
    optimizer_phase: str
    seed: int
    iteration: int
    parameters: dict[str, Any]
    simulation_status: str
    metrics: dict[str, float | None]
    ugf_status: str
    phase_margin_status: str
    ugf_crossing_count: int
    positive_slew_status: str
    negative_slew_status: str
    operating_region_valid: bool | None
    operating_region_mask: int
    operating_region_types: tuple[str, ...]
    device_status: dict[str, str]
    device_quantities: dict[str, dict[str, float]]
    analysis_errors: dict[str, str | None]
    objective_value: float | None
    constraint_violation: float | None
    constraint_components: dict[str, float]
    is_feasible: bool
    event_observed: bool
    candidate_evaluations: int
    ngspice_process_calls: int
    op_calls: int
    ac_calls: int
    transient_calls: int
    high_fidelity_analysis_calls: int
    screening_calls: int
    op_runtime_seconds: float
    ac_runtime_seconds: float
    transient_runtime_seconds: float
    wall_clock_seconds: float
    total_elapsed_time: float
    candidate_evaluations_cumulative: int
    ngspice_process_calls_cumulative: int
    op_calls_cumulative: int
    ac_calls_cumulative: int
    transient_calls_cumulative: int
    high_fidelity_analysis_calls_cumulative: int
    screening_calls_cumulative: int
    timestamp: str
    run_directory: str
    task7_benchmark_hash: str
    task7_search_space_hash: str
    task7_protocol_family_hash: str

    def __post_init__(self) -> None:
        if self.experiment_design not in {"smoke", "formal"}:
            raise ValueError("invalid Task 7 experiment design")
        if self.seed < 0 or self.iteration <= 0:
            raise ValueError("Task 7 seed/iteration is invalid")
        if self.candidate_evaluations != 1:
            raise ValueError("every Task 7 row represents exactly one candidate")
        if self.screening_calls != 0 or self.screening_calls_cumulative != 0:
            raise ValueError("Task 7 forbids screening calls")
        counts = (
            self.ngspice_process_calls,
            self.op_calls,
            self.ac_calls,
            self.transient_calls,
            self.high_fidelity_analysis_calls,
        )
        if counts != (3, 1, 1, 1, 3):
            raise ValueError("Task 7 Full row must account for 3/1/1/1/3 calls")
        for name in (
            "ugf_crossing_count",
            "operating_region_mask",
            "candidate_evaluations_cumulative",
            "ngspice_process_calls_cumulative",
            "op_calls_cumulative",
            "ac_calls_cumulative",
            "transient_calls_cumulative",
            "high_fidelity_analysis_calls_cumulative",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in (
            "op_runtime_seconds",
            "ac_runtime_seconds",
            "transient_runtime_seconds",
            "wall_clock_seconds",
            "total_elapsed_time",
        ):
            value = float(getattr(self, name))
            if not isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        for value in self.metrics.values():
            if value is not None and not isfinite(float(value)):
                raise ValueError("Task 7 metrics must be finite or null")
        if self.simulation_status == "success":
            if self.objective_value is None or self.constraint_violation is None:
                raise ValueError("successful Task 7 row requires optimizer feedback")
        elif self.objective_value is not None or self.is_feasible:
            raise ValueError("failed Task 7 row cannot have successful feedback")
        if self.is_feasible and float(self.constraint_violation or 0.0) != 0.0:
            raise ValueError("feasible Task 7 row cannot have a violation")
        for name in (
            "task7_benchmark_hash",
            "task7_search_space_hash",
            "task7_protocol_family_hash",
        ):
            value = getattr(self, name)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{name} must be a lowercase SHA-256")

    @classmethod
    def now(cls, **values: Any) -> "Task7EvaluationRecord":
        return cls(
            **values,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        )


class Task7Recorder:
    """Write a committed SQLite row before atomically mirroring canonical CSV."""

    SCHEMA_VERSION = 1

    def __init__(self, output_directory: Path) -> None:
        self.output_directory = output_directory.resolve()
        self.csv_path = self.output_directory / "evaluations.csv"
        self.database_path = self.output_directory / "evaluations.sqlite3"
        self.output_directory.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS task7_evaluations("
                "run_id TEXT NOT NULL,iteration INTEGER NOT NULL,"
                "payload_json TEXT NOT NULL,PRIMARY KEY(run_id,iteration))"
            )
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, self.SCHEMA_VERSION}:
                raise ResearchExperimentError(
                    f"unsupported Task 7 recorder schema {version}"
                )
            connection.execute(f"PRAGMA user_version={self.SCHEMA_VERSION}")
        self._write_csv(self.records())

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _payload(record: Task7EvaluationRecord) -> dict[str, Any]:
        result = {name: getattr(record, name) for name in TASK7_COLUMNS}
        result["operating_region_types"] = list(record.operating_region_types)
        return result

    @staticmethod
    def _record(payload: Mapping[str, Any]) -> Task7EvaluationRecord:
        values = dict(payload)
        values["operating_region_types"] = tuple(values["operating_region_types"])
        return Task7EvaluationRecord(**values)

    def records(self) -> tuple[Task7EvaluationRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM task7_evaluations ORDER BY iteration"
            ).fetchall()
        try:
            return tuple(
                self._record(json.loads(row["payload_json"])) for row in rows
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ResearchExperimentError(f"invalid Task 7 recorder payload: {exc}") from exc

    def save(self, record: Task7EvaluationRecord) -> None:
        payload = json.dumps(
            self._payload(record), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO task7_evaluations(run_id,iteration,payload_json) "
                    "VALUES(?,?,?)",
                    (record.run_id, record.iteration, payload),
                )
        except sqlite3.IntegrityError as exc:
            raise ResearchExperimentError(
                f"Task 7 evaluation {record.iteration} already exists"
            ) from exc
        self._write_csv(self.records())

    def _write_csv(self, records: tuple[Task7EvaluationRecord, ...]) -> None:
        temporary = self.csv_path.with_name(f".{self.csv_path.name}.tmp")
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=TASK7_COLUMNS)
            writer.writeheader()
            for record in records:
                row = self._payload(record)
                for name in JSON_FIELDS:
                    row[name] = json.dumps(
                        row[name], sort_keys=True, separators=(",", ":"), allow_nan=False
                    )
                for name in (
                    "operating_region_valid",
                    "objective_value",
                    "constraint_violation",
                ):
                    if row[name] is None:
                        row[name] = ""
                row["is_feasible"] = str(record.is_feasible).lower()
                row["event_observed"] = str(record.event_observed).lower()
                writer.writerow(row)
        last_error: PermissionError | None = None
        for delay in (0.0, 0.01, 0.05, 0.1, 0.25, 0.5):
            if delay:
                sleep(delay)
            try:
                temporary.replace(self.csv_path)
                return
            except PermissionError as exc:
                last_error = exc
        assert last_error is not None
        raise ResearchExperimentError(
            f"failed to atomically replace Task 7 CSV: {last_error}"
        ) from last_error
