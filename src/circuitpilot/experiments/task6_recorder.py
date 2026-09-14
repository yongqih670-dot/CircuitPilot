"""Task 6 candidate-level SQLite and CSV evidence."""

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
from circuitpilot.task6_protocol import FULL_POLICY, SCREENED_POLICY


TASK6_COLUMNS = (
    "experiment_id",
    "run_id",
    "method",
    "evaluation_policy",
    "optimizer_phase",
    "seed",
    "iteration",
    "parameters",
    "simulation_status",
    "measurement_status",
    "evaluation_stage",
    "physics_status",
    "physics_violation_mask",
    "physics_violation_count",
    "physics_violation_types",
    "op_constraint_violation",
    "bandwidth_status",
    "bandwidth_lower_bound_hz",
    "cmrr_status",
    "cmrr_lower_bound_db",
    "failure_type",
    "error_message",
    "policy_message",
    "raw_metrics",
    "objective_value",
    "constraint_violation",
    "is_feasible",
    "candidate_evaluations",
    "ngspice_process_calls",
    "dc_op_calls",
    "differential_ac_calls",
    "common_mode_ac_calls",
    "full_ac_candidate_count",
    "expensive_ac_analysis_count",
    "physical_analysis_calls",
    "expensive_ac_calls_cumulative",
    "wall_clock_seconds",
    "total_elapsed_time",
    "timestamp",
    "run_directory",
    "task5_benchmark_hash",
    "evaluation_policy_hash",
    "task6_policy_family_hash",
    "experiment_design",
    "event_observed",
)


def _optional_finite(value: float | None, name: str) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError(f"{name} must be finite or null")
    return numeric


@dataclass(frozen=True, slots=True)
class Task6EvaluationRecord:
    """One immutable Task 6 candidate record."""

    experiment_id: str
    run_id: str
    method: str
    evaluation_policy: str
    optimizer_phase: str
    seed: int
    iteration: int
    parameters: dict[str, Any]
    simulation_status: str
    measurement_status: str | None
    evaluation_stage: str | None
    physics_status: str | None
    physics_violation_mask: int
    physics_violation_count: int
    physics_violation_types: tuple[str, ...]
    op_constraint_violation: float | None
    bandwidth_status: str | None
    bandwidth_lower_bound_hz: float | None
    cmrr_status: str | None
    cmrr_lower_bound_db: float | None
    failure_type: str | None
    error_message: str | None
    policy_message: str | None
    raw_metrics: dict[str, float | None]
    objective_value: float | None
    constraint_violation: float | None
    is_feasible: bool
    candidate_evaluations: int
    ngspice_process_calls: int
    dc_op_calls: int
    differential_ac_calls: int
    common_mode_ac_calls: int
    full_ac_candidate_count: int
    expensive_ac_analysis_count: int
    physical_analysis_calls: int
    expensive_ac_calls_cumulative: int
    wall_clock_seconds: float
    total_elapsed_time: float
    timestamp: str
    run_directory: str
    task5_benchmark_hash: str
    evaluation_policy_hash: str
    task6_policy_family_hash: str
    experiment_design: str
    event_observed: bool

    def __post_init__(self) -> None:
        for name in (
            "experiment_id",
            "run_id",
            "method",
            "optimizer_phase",
            "simulation_status",
            "timestamp",
            "run_directory",
            "experiment_design",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(
                self, name
            ):
                raise ValueError(f"{name} must be non-empty")
        if self.evaluation_policy not in {FULL_POLICY, SCREENED_POLICY}:
            raise ValueError("invalid Task 6 evaluation policy")
        if self.measurement_status not in {
            None,
            "complete",
            "op_only_complete",
            "invalid_response",
            "analysis_error",
        }:
            raise ValueError("invalid Task 6 measurement status")
        if self.evaluation_stage not in {
            None,
            "op_rejected",
            "full_evaluated",
        }:
            raise ValueError("invalid Task 6 evaluation stage")
        if self.physics_status not in {None, "valid", "invalid"}:
            raise ValueError("invalid Task 6 physics status")
        if self.seed < 0 or self.iteration <= 0:
            raise ValueError("seed/iteration are invalid")
        if self.candidate_evaluations != 1:
            raise ValueError("every Task 6 row must account for one candidate")
        for name in (
            "physics_violation_mask",
            "physics_violation_count",
            "ngspice_process_calls",
            "dc_op_calls",
            "differential_ac_calls",
            "common_mode_ac_calls",
            "full_ac_candidate_count",
            "expensive_ac_analysis_count",
            "physical_analysis_calls",
            "expensive_ac_calls_cumulative",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.expensive_ac_analysis_count != (
            self.differential_ac_calls + self.common_mode_ac_calls
        ):
            raise ValueError("expensive AC count must equal both logical AC counts")
        if self.full_ac_candidate_count not in {0, 1}:
            raise ValueError("full_ac_candidate_count must be zero or one")
        expected_full = int(
            self.differential_ac_calls == 1 and self.common_mode_ac_calls == 1
        )
        if self.full_ac_candidate_count != expected_full:
            raise ValueError("full-AC candidate count is inconsistent")
        if self.physics_violation_count == 0:
            if self.physics_violation_mask != 0 or self.physics_violation_types:
                raise ValueError("valid physics cannot contain violation evidence")
        elif self.physics_violation_mask == 0 or not self.physics_violation_types:
            raise ValueError("physics violations require mask and types")
        if self.physics_status == "valid" and self.physics_violation_count != 0:
            raise ValueError("valid physics cannot contain violations")
        if self.physics_status == "invalid" and self.physics_violation_count == 0:
            raise ValueError("invalid physics requires violations")
        if self.evaluation_stage == "op_rejected":
            if (
                self.evaluation_policy != SCREENED_POLICY
                or self.physics_status != "invalid"
                or self.measurement_status != "op_only_complete"
                or self.differential_ac_calls
                or self.common_mode_ac_calls
                or self.is_feasible
            ):
                raise ValueError("OP-rejected record semantics are inconsistent")
            for metric in (
                "differential_gain_db",
                "common_mode_gain_db",
                "bandwidth_hz",
                "bandwidth_lower_bound_hz",
                "cmrr_db",
                "cmrr_lower_bound_db",
            ):
                if self.raw_metrics.get(metric) is not None:
                    raise ValueError("OP-rejected AC metrics must remain null")
        if self.is_feasible and self.evaluation_stage != "full_evaluated":
            raise ValueError("only a full-evaluated candidate can be feasible")
        for name in (
            "op_constraint_violation",
            "bandwidth_lower_bound_hz",
            "cmrr_lower_bound_db",
            "objective_value",
            "constraint_violation",
            "wall_clock_seconds",
            "total_elapsed_time",
        ):
            _optional_finite(getattr(self, name), name)
        if self.wall_clock_seconds < 0 or self.total_elapsed_time < 0:
            raise ValueError("wall-clock fields must be non-negative")
        if self.constraint_violation is not None and self.constraint_violation < 0:
            raise ValueError("constraint violation must be non-negative")
        for value in self.raw_metrics.values():
            _optional_finite(value, "raw metric")
        for name in (
            "task5_benchmark_hash",
            "evaluation_policy_hash",
            "task6_policy_family_hash",
        ):
            value = getattr(self, name)
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(f"{name} must be a lowercase SHA-256")
        if self.simulation_status == "success":
            if self.objective_value is None:
                if self.constraint_violation is not None or self.is_feasible:
                    raise ValueError("incomplete analysis cannot contain optimizer feedback")
                if self.measurement_status not in {
                    "invalid_response",
                    "analysis_error",
                }:
                    raise ValueError(
                        "successful Task 6 simulation without feedback requires "
                        "an explicit analysis status"
                    )
            elif self.constraint_violation is None:
                raise ValueError("successful optimizer feedback must be complete")
        elif self.objective_value is not None or self.is_feasible:
            raise ValueError("failed Task 6 simulation cannot contain success feedback")

    @classmethod
    def now(cls, **values: Any) -> "Task6EvaluationRecord":
        return cls(
            **values,
            timestamp=datetime.now(timezone.utc).isoformat(timespec="microseconds"),
        )


class Task6Recorder:
    """Persist Task 6 rows transactionally and mirror them to canonical CSV."""

    SCHEMA_VERSION = 1

    def __init__(self, output_directory: Path) -> None:
        self.output_directory = output_directory.resolve()
        self.csv_path = self.output_directory / "evaluations.csv"
        self.database_path = self.output_directory / "evaluations.sqlite3"
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._write_csv(self.records())

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS task6_evaluations (
                    run_id TEXT NOT NULL,
                    iteration INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, iteration)
                );
                """
            )
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, self.SCHEMA_VERSION}:
                raise ResearchExperimentError(
                    f"unsupported Task 6 recorder schema {version}"
                )
            connection.execute(f"PRAGMA user_version={self.SCHEMA_VERSION}")

    @staticmethod
    def _to_payload(record: Task6EvaluationRecord) -> dict[str, Any]:
        return {
            name: (
                list(value)
                if name == "physics_violation_types"
                else value
            )
            for name, value in (
                (column, getattr(record, column))
                for column in TASK6_COLUMNS
            )
        }

    @staticmethod
    def _from_payload(payload: Mapping[str, Any]) -> Task6EvaluationRecord:
        values = dict(payload)
        values["physics_violation_types"] = tuple(
            values["physics_violation_types"]
        )
        return Task6EvaluationRecord(**values)

    def save(self, record: Task6EvaluationRecord) -> None:
        payload = json.dumps(
            self._to_payload(record),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        try:
            with self._connect() as connection:
                connection.execute(
                    "INSERT INTO task6_evaluations(run_id,iteration,payload_json) "
                    "VALUES(?,?,?)",
                    (record.run_id, record.iteration, payload),
                )
        except sqlite3.IntegrityError as exc:
            raise ResearchExperimentError(
                f"Task 6 evaluation {record.iteration} already exists"
            ) from exc
        self._write_csv(self.records())

    def records(self) -> tuple[Task6EvaluationRecord, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM task6_evaluations ORDER BY iteration"
            ).fetchall()
        try:
            return tuple(
                self._from_payload(json.loads(row["payload_json"]))
                for row in rows
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ResearchExperimentError(
                f"invalid Task 6 recorder payload: {exc}"
            ) from exc

    def _write_csv(self, records: tuple[Task6EvaluationRecord, ...]) -> None:
        temporary = self.csv_path.with_name(f".{self.csv_path.name}.tmp")
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=TASK6_COLUMNS)
            writer.writeheader()
            for record in records:
                row = self._to_payload(record)
                for name in (
                    "parameters",
                    "raw_metrics",
                    "physics_violation_types",
                ):
                    row[name] = json.dumps(
                        row[name],
                        sort_keys=True,
                        separators=(",", ":"),
                        allow_nan=False,
                    )
                for name in (
                    "measurement_status",
                    "evaluation_stage",
                    "physics_status",
                    "op_constraint_violation",
                    "bandwidth_status",
                    "bandwidth_lower_bound_hz",
                    "cmrr_status",
                    "cmrr_lower_bound_db",
                    "failure_type",
                    "error_message",
                    "policy_message",
                    "objective_value",
                    "constraint_violation",
                ):
                    if row[name] is None:
                        row[name] = ""
                row["is_feasible"] = str(record.is_feasible).lower()
                row["event_observed"] = str(record.event_observed).lower()
                writer.writerow(row)
        last_error: PermissionError | None = None
        for delay_seconds in (0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0):
            if delay_seconds:
                sleep(delay_seconds)
            try:
                temporary.replace(self.csv_path)
                return
            except PermissionError as exc:
                last_error = exc
        assert last_error is not None
        raise ResearchExperimentError(
            f"failed to atomically replace Task 6 CSV after retries: {last_error}"
        ) from last_error
