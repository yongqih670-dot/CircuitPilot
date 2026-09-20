"""Budgeted, resumable optimizer execution for Research Task 9."""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Mapping

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.config import ExperimentConfig, load_experiment_config, write_experiment_config
from circuitpilot.experiments.optimizers.base import Optimizer
from circuitpilot.experiments.optimizers.factory import create_optimizer
from circuitpilot.experiments.seeding import initialize_seeds
from circuitpilot.experiments.task9_evaluator import Task9Evaluation, evaluate_task9_candidate
from circuitpilot.run_directory import prepare_research_run_directory
from circuitpilot.sky130_two_stage_ota import Sky130TwoStageOtaCircuitConfig
from circuitpilot.task7_protocol import METHODS, TASK7_BENCHMARK_HASH, TASK7_COMPONENT_HASHES, TASK7_SEARCH_SPACE_HASH, stable_hash
from circuitpilot.task9_protocol import (
    CORNER_ORDER_HASH,
    CORNER_SUITE_HASH,
    COST_ACCOUNTING_HASH,
    PARTIAL_FEEDBACK_HASH,
    PVT_BENCHMARK_HASH,
    PVT_EVALUATION_POLICY_HASH,
    SIMULATION_TIME_BUDGET_HASH,
    TASK9_PROTOCOL_HASH,
    policy_hash,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
TASK9_ROOT = PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task9"
TASK9_MANIFEST = TASK9_ROOT / "task9_protocol_manifest.json"
JSON_FIELDS = {
    "parameters",
    "corner_results",
    "worst_metrics",
    "constraint_components",
    "feedback_tier",
    "shadow_analysis_errors",
}


@dataclass(frozen=True, slots=True)
class Task9RunDefinition:
    base_config_path: Path
    method: str
    policy: str
    seed: int
    experiment_design: str
    output_root: Path
    candidate_budget: int | None = None
    simulation_time_budget_seconds: float | None = None
    candidate_cap: int | None = None
    shadow_audit: bool = False

    def __post_init__(self) -> None:
        if self.method not in METHODS:
            raise ValueError(f"unsupported Task 9 method '{self.method}'")
        if self.policy not in {"full", "hierarchical"}:
            raise ValueError("Task 9 policy must be full or hierarchical")
        if self.experiment_design not in {"smoke", "equal_candidate", "equal_simulation_time"}:
            raise ValueError("invalid Task 9 experiment design")
        if self.seed < 0:
            raise ValueError("Task 9 seed must be non-negative")
        if self.experiment_design == "equal_simulation_time":
            if (
                self.simulation_time_budget_seconds is None
                or self.simulation_time_budget_seconds <= 0
                or self.candidate_cap is None
                or self.candidate_cap <= 0
                or self.candidate_budget is not None
            ):
                raise ValueError("equal-time design requires time budget and cap only")
        elif (
            self.candidate_budget is None
            or self.candidate_budget <= 0
            or self.simulation_time_budget_seconds is not None
        ):
            raise ValueError("candidate design requires a positive candidate budget")
        if self.shadow_audit and (
            self.experiment_design != "smoke" or self.policy != "hierarchical"
        ):
            raise ValueError("shadow audit is only valid for Hierarchical smoke")

    @property
    def experiment_id(self) -> str:
        return f"task9_{self.experiment_design}_{self.policy}_{self.method}_seed{self.seed}"

    def semantic_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "task9_run_definition_v1",
            "experiment_id": self.experiment_id,
            "experiment_design": self.experiment_design,
            "method": self.method,
            "policy": self.policy,
            "seed": self.seed,
            "candidate_budget": self.candidate_budget,
            "simulation_time_budget_seconds": self.simulation_time_budget_seconds,
            "candidate_cap": self.candidate_cap,
            "shadow_audit": self.shadow_audit,
            "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
            "task7_search_space_hash": TASK7_SEARCH_SPACE_HASH,
            "task9_protocol_hash": TASK9_PROTOCOL_HASH,
            "pvt_benchmark_hash": PVT_BENCHMARK_HASH,
            "corner_suite_hash": CORNER_SUITE_HASH,
            "corner_order_hash": CORNER_ORDER_HASH,
            "pvt_evaluation_policy_hash": PVT_EVALUATION_POLICY_HASH,
            "policy_hash": policy_hash(self.policy),
            "partial_feedback_hash": PARTIAL_FEEDBACK_HASH,
            "simulation_time_budget_hash": SIMULATION_TIME_BUDGET_HASH,
            "cost_accounting_hash": COST_ACCOUNTING_HASH,
        }

    def identity_sha256(self) -> str:
        return stable_hash(self.semantic_dict())

    def resolved_config(self) -> ExperimentConfig:
        config = load_experiment_config(self.base_config_path)
        if (
            config.computed_benchmark_hash() != TASK7_BENCHMARK_HASH
            or config.search_space_sha256() != TASK7_SEARCH_SPACE_HASH
        ):
            raise ResearchExperimentError("Task 7 frozen benchmark identity drifted")
        return replace(
            config,
            experiment_name=self.experiment_id,
            method=self.method,
            seed=self.seed,
            simulation_budget=(
                int(self.candidate_cap or 1)
                if self.experiment_design == "equal_simulation_time"
                else int(self.candidate_budget or 1)
            ),
            output_dir=self.output_root,
            experiment_phase="smoke" if self.experiment_design == "smoke" else "baseline",
            resume=False,
        )


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def validate_frozen_protocol() -> dict[str, Any]:
    try:
        manifest = json.loads(TASK9_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResearchExperimentError(f"cannot read Task 9 protocol manifest: {exc}") from exc
    if manifest.get("hashes", {}).get("task9_protocol_hash") != TASK9_PROTOCOL_HASH:
        raise ResearchExperimentError("Task 9 protocol hash drifted")
    for name, expected in manifest["frozen_document_hashes"].items():
        path = TASK9_ROOT / name
        if not path.is_file() or _hash(path) != expected:
            raise ResearchExperimentError(f"frozen Task 9 input drifted: {name}")
    frozen = TASK9_ROOT / "task9_pvt_ota_frozen.yaml"
    if _hash(frozen) != manifest["frozen_yaml_sha256"]:
        raise ResearchExperimentError("Task 9 frozen YAML bytes drifted")
    return manifest


def fairness_identity(definition: Task9RunDefinition, config: ExperimentConfig) -> dict[str, Any]:
    return {
        "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
        "task7_search_space_hash": TASK7_SEARCH_SPACE_HASH,
        "task7_component_hashes": dict(TASK7_COMPONENT_HASHES),
        "task9_protocol_hash": TASK9_PROTOCOL_HASH,
        "pvt_benchmark_hash": PVT_BENCHMARK_HASH,
        "corner_suite_hash": CORNER_SUITE_HASH,
        "corner_order_hash": CORNER_ORDER_HASH,
        "pvt_evaluation_policy_hash": PVT_EVALUATION_POLICY_HASH,
        "partial_feedback_hash": PARTIAL_FEEDBACK_HASH,
        "simulation_time_budget_hash": SIMULATION_TIME_BUDGET_HASH,
        "cost_accounting_hash": COST_ACCOUNTING_HASH,
        "method": definition.method,
        "seed": definition.seed,
        "experiment_design": definition.experiment_design,
        "candidate_budget": definition.candidate_budget,
        "simulation_time_budget_seconds": definition.simulation_time_budget_seconds,
        "candidate_cap": definition.candidate_cap,
        "optimizer_config_hash": stable_hash(dict(config.optimizer_config)),
        "policy_hash": policy_hash(definition.policy),
    }


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResearchExperimentError(f"invalid Task 9 record store: {exc}") from exc
    if not isinstance(value, list):
        raise ResearchExperimentError("Task 9 record store must contain a list")
    return value


def _write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        for record in records:
            row = dict(record)
            for name in JSON_FIELDS:
                row[name] = json.dumps(row[name], sort_keys=True, separators=(",", ":"), allow_nan=False)
            for name, value in row.items():
                if value is None:
                    row[name] = ""
                elif isinstance(value, bool):
                    row[name] = str(value).lower()
            writer.writerow(row)
    temporary.replace(path)


def _save_records(run_directory: Path, records: list[dict[str, Any]]) -> None:
    _atomic_json(run_directory / "records.json", records)
    _write_csv(run_directory / "evaluations.csv", records)


def _optimizer_feedback(record: Mapping[str, Any]) -> tuple[dict[str, float], float | None, str]:
    status = str(record["simulation_status"])
    if status != "success":
        return {}, None, status
    metrics = {
        name: float(value)
        for name, value in record["worst_metrics"].items()
        if value is not None and not name.startswith("worst_corner_for_")
    }
    metrics["progress_units"] = float(record["progress_units"])
    metrics["pvt_feasible"] = float(bool(record["is_feasible"]))
    return metrics, float(record["objective_value"]), status


def _save_optimizer_state(optimizer: Optimizer, path: Path) -> None:
    last_error: ResearchExperimentError | None = None
    for delay in (0.0, 0.01, 0.05, 0.1, 0.25, 0.5):
        if delay:
            sleep(delay)
        try:
            optimizer.save_state(path)
            return
        except ResearchExperimentError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _empty_shadow() -> dict[str, Any]:
    return {
        "performed": False,
        "full_is_feasible": None,
        "false_rejection": False,
        "process_calls": 0,
        "op_calls": 0,
        "ac_calls": 0,
        "transient_calls": 0,
        "accumulated_ngspice_seconds": 0.0,
        "outer_wall_seconds": 0.0,
        "analysis_errors": {},
    }


def _shadow_validate(
    primary: Task9Evaluation,
    *,
    config: ExperimentConfig,
    parameters: Mapping[str, float | int],
    directory: Path,
) -> dict[str, Any]:
    circuit = config.circuit_config
    assert isinstance(circuit, Sky130TwoStageOtaCircuitConfig)
    full = evaluate_task9_candidate(
        policy="full",
        base_config=circuit,
        parameters=parameters,
        evaluation_directory=directory,
        executable=config.ngspice_config.executable,
        timeout_seconds=config.timeout,
        start_frequency_hz=config.ngspice_config.start_frequency_hz,
        stop_frequency_hz=config.ngspice_config.stop_frequency_hz,
        points_per_decade=config.ngspice_config.points_per_decade,
    )
    errors = {
        corner["corner_id"]: corner["analysis_errors"]
        for corner in full.corner_results
        if any(corner["analysis_errors"].values())
    }
    return {
        "performed": True,
        "full_is_feasible": full.is_feasible,
        "false_rejection": full.is_feasible and not primary.is_feasible,
        "process_calls": full.process_calls,
        "op_calls": full.op_calls,
        "ac_calls": full.ac_calls,
        "transient_calls": full.transient_calls,
        "accumulated_ngspice_seconds": full.accumulated_ngspice_seconds,
        "outer_wall_seconds": full.outer_wall_seconds,
        "analysis_errors": errors,
    }


def _summary(
    definition: Task9RunDefinition,
    config: ExperimentConfig,
    run_id: str,
    records: list[dict[str, Any]],
    elapsed_seconds: float,
) -> dict[str, Any]:
    first = next((row for row in records if row["event_observed"]), None)
    accumulated = 0.0 if not records else float(records[-1]["accumulated_ngspice_seconds_cumulative"])
    time_budget = definition.simulation_time_budget_seconds
    return {
        **definition.semantic_dict(),
        "run_id": run_id,
        "completed": (
            len(records) >= int(definition.candidate_budget or 0)
            if definition.experiment_design != "equal_simulation_time"
            else accumulated >= float(time_budget or 0.0) or len(records) >= int(definition.candidate_cap or 0)
        ),
        "fairness_identity": fairness_identity(definition, config),
        "candidate_count": len(records),
        "completed_candidate_count": sum(bool(row["candidate_completed"]) for row in records),
        "budget_terminal_candidate_count": sum(
            bool(row["budget_terminal_candidate"]) for row in records
        ),
        "corners_started": sum(int(row["corners_started"]) for row in records),
        "corners_completed": sum(int(row["corners_completed"]) for row in records),
        "op_calls": sum(int(row["op_calls"]) for row in records),
        "ac_calls": sum(int(row["ac_calls"]) for row in records),
        "transient_calls": sum(int(row["transient_calls"]) for row in records),
        "process_calls": sum(int(row["process_calls"]) for row in records),
        "accumulated_ngspice_seconds": accumulated,
        "outer_wall_seconds": sum(float(row["outer_wall_seconds"]) for row in records),
        "orchestration_seconds": sum(float(row["orchestration_seconds"]) for row in records),
        "budget_overshoot_seconds": 0.0 if time_budget is None else max(0.0, accumulated - float(time_budget)),
        "event_observed": first is not None,
        "feasible_candidates": sum(bool(row["is_feasible"]) for row in records),
        "candidate_time_to_first_feasible": None if first is None else first["candidate_count_cumulative"],
        "corner_time_to_first_feasible": None if first is None else first["corners_started_cumulative"],
        "op_time_to_first_feasible": None if first is None else first["op_calls_cumulative"],
        "ac_time_to_first_feasible": None if first is None else first["ac_calls_cumulative"],
        "transient_time_to_first_feasible": None if first is None else first["transient_calls_cumulative"],
        "ngspice_time_to_first_feasible": None if first is None else first["accumulated_ngspice_seconds_cumulative"],
        "shadow_audit_candidates": sum(bool(row["shadow_validation_performed"]) for row in records),
        "shadow_false_rejection_count": sum(bool(row["shadow_false_rejection"]) for row in records),
        "shadow_process_calls": sum(int(row["shadow_process_calls"]) for row in records),
        "shadow_accumulated_ngspice_seconds": sum(float(row["shadow_accumulated_ngspice_seconds"]) for row in records),
        "run_elapsed_seconds": elapsed_seconds,
    }


def execute_task9_run(
    definition: Task9RunDefinition,
    *,
    resume_directory: str | Path | None = None,
    optimizer: Optimizer | None = None,
    max_new_candidates: int | None = None,
) -> tuple[Path, dict[str, Any]]:
    validate_frozen_protocol()
    config = definition.resolved_config()
    circuit = config.circuit_config
    if not isinstance(circuit, Sky130TwoStageOtaCircuitConfig):
        raise ResearchExperimentError("Task 9 requires the typed two-stage OTA")
    run = prepare_research_run_directory(
        resume_directory,
        resume=resume_directory is not None,
        default_root=definition.output_root,
        configuration_sha256=definition.identity_sha256(),
    )
    for directory in (run.path / "runs", run.path / "summary"):
        directory.mkdir(parents=True, exist_ok=True)
    definition_path = run.path / "task9_run_definition.json"
    if run.resumed:
        if json.loads(definition_path.read_text(encoding="utf-8")) != definition.semantic_dict():
            raise ResearchExperimentError("resumed Task 9 definition changed")
    else:
        _atomic_json(definition_path, definition.semantic_dict())
        write_experiment_config(config, run.path / "experiment_config.yaml")
    selected_optimizer = optimizer or create_optimizer(config, initialize_seeds(definition.seed))
    state_path = run.path / "summary" / "optimizer_state.json"
    records_path = run.path / "records.json"
    inflight_path = run.path / "inflight.json"
    records = _load_records(records_path)
    if run.resumed and state_path.is_file():
        selected_optimizer.load_state(state_path)
    elif records:
        raise ResearchExperimentError("Task 9 records exist without optimizer state")
    if inflight_path.is_file() and records:
        inflight = json.loads(inflight_path.read_text(encoding="utf-8"))
        if int(inflight["iteration"]) == len(records):
            record = records[-1]
            metrics, objective, status = _optimizer_feedback(record)
            if len(selected_optimizer.get_history()) < len(records):
                replayed = selected_optimizer.ask()
                if replayed != record["parameters"]:
                    raise ResearchExperimentError("Task 9 optimizer candidate drifted during reconciliation")
                selected_optimizer.tell(record["parameters"], metrics, objective, status)
                _save_optimizer_state(selected_optimizer, state_path)
            inflight_path.unlink()
    elapsed_offset = 0.0 if not records else float(records[-1]["total_elapsed_time"])
    started = monotonic()
    event_seen = any(bool(row["is_feasible"]) for row in records)
    new_count = 0
    while True:
        accumulated = 0.0 if not records else float(records[-1]["accumulated_ngspice_seconds_cumulative"])
        if definition.experiment_design == "equal_simulation_time":
            if accumulated >= float(definition.simulation_time_budget_seconds or 0.0) or len(records) >= int(definition.candidate_cap or 0):
                break
        elif len(records) >= int(definition.candidate_budget or 0):
            break
        if max_new_candidates is not None and new_count >= max_new_candidates:
            break
        if inflight_path.is_file():
            inflight = json.loads(inflight_path.read_text(encoding="utf-8"))
            parameters = inflight["parameters"]
            iteration = int(inflight["iteration"])
            optimizer_phase = inflight["optimizer_phase"]
            if selected_optimizer.ask() != parameters:
                raise ResearchExperimentError("Task 9 optimizer candidate drifted during stage resume")
        else:
            _save_optimizer_state(selected_optimizer, state_path)
            parameters = selected_optimizer.ask()
            config.validate_parameters(parameters)
            optimizer_phase = selected_optimizer.get_last_ask_metadata().get("optimizer_phase", "search")
            iteration = len(records) + 1
            _atomic_json(
                inflight_path,
                {"schema_version": 1, "iteration": iteration, "parameters": parameters, "optimizer_phase": optimizer_phase},
            )
        evaluation_directory = run.path / "runs" / f"evaluation_{iteration:04d}"
        evaluation = evaluate_task9_candidate(
            policy=definition.policy,
            base_config=circuit,
            parameters=parameters,
            evaluation_directory=evaluation_directory,
            executable=config.ngspice_config.executable,
            timeout_seconds=config.timeout,
            start_frequency_hz=config.ngspice_config.start_frequency_hz,
            stop_frequency_hz=config.ngspice_config.stop_frequency_hz,
            points_per_decade=config.ngspice_config.points_per_decade,
            stop_after_accumulated_ngspice_seconds=(
                None
                if definition.simulation_time_budget_seconds is None
                else definition.simulation_time_budget_seconds - accumulated
            ),
        )
        shadow = _empty_shadow()
        if definition.shadow_audit and not evaluation.is_feasible:
            shadow = _shadow_validate(
                evaluation,
                config=config,
                parameters=parameters,
                directory=evaluation_directory / "shadow_full",
            )
        event_observed = evaluation.is_feasible and not event_seen
        event_seen = event_seen or evaluation.is_feasible
        previous = records[-1] if records else None

        def cumulative(field: str, value: int) -> int:
            return (0 if previous is None else int(previous[field])) + value

        record = {
            "experiment_id": definition.experiment_id,
            "run_id": run.run_id,
            "experiment_design": definition.experiment_design,
            "policy": definition.policy,
            "method": definition.method,
            "optimizer_phase": optimizer_phase,
            "seed": definition.seed,
            "iteration": iteration,
            "parameters": dict(parameters),
            "simulation_status": evaluation.simulation_status,
            "evaluation_stage": evaluation.evaluation_stage,
            "candidate_completed": evaluation.simulation_status != "budget_exhausted",
            "budget_terminal_candidate": evaluation.simulation_status == "budget_exhausted",
            "first_failing_corner": evaluation.first_failing_corner,
            "first_failing_stage": evaluation.first_failing_stage,
            "first_failing_constraint": evaluation.first_failing_constraint,
            "corner_results": list(evaluation.corner_results),
            "worst_metrics": evaluation.worst_metrics,
            "objective_value": evaluation.objective_value,
            "robust_constraint_violation": evaluation.robust_constraint_violation,
            "constraint_components": evaluation.constraint_components,
            "is_feasible": evaluation.is_feasible,
            "event_observed": event_observed,
            "progress_units": evaluation.progress_units,
            "feedback_tier": list(evaluation.feedback_tier),
            "candidate_count": 1,
            "corners_started": evaluation.corners_started,
            "corners_completed": evaluation.corners_completed,
            "op_calls": evaluation.op_calls,
            "ac_calls": evaluation.ac_calls,
            "transient_calls": evaluation.transient_calls,
            "process_calls": evaluation.process_calls,
            "accumulated_ngspice_seconds": evaluation.accumulated_ngspice_seconds,
            "outer_wall_seconds": evaluation.outer_wall_seconds,
            "orchestration_seconds": evaluation.orchestration_seconds,
            "process_elapsed_estimate_count": evaluation.process_elapsed_estimate_count,
            "candidate_count_cumulative": iteration,
            "corners_started_cumulative": cumulative("corners_started_cumulative", evaluation.corners_started),
            "corners_completed_cumulative": cumulative("corners_completed_cumulative", evaluation.corners_completed),
            "op_calls_cumulative": cumulative("op_calls_cumulative", evaluation.op_calls),
            "ac_calls_cumulative": cumulative("ac_calls_cumulative", evaluation.ac_calls),
            "transient_calls_cumulative": cumulative("transient_calls_cumulative", evaluation.transient_calls),
            "process_calls_cumulative": cumulative("process_calls_cumulative", evaluation.process_calls),
            "accumulated_ngspice_seconds_cumulative": (
                (0.0 if previous is None else float(previous["accumulated_ngspice_seconds_cumulative"]))
                + evaluation.accumulated_ngspice_seconds
            ),
            "total_elapsed_time": elapsed_offset + monotonic() - started,
            "budget_overshoot_seconds": (
                0.0
                if definition.simulation_time_budget_seconds is None
                else max(
                    0.0,
                    (0.0 if previous is None else float(previous["accumulated_ngspice_seconds_cumulative"]))
                    + evaluation.accumulated_ngspice_seconds
                    - definition.simulation_time_budget_seconds,
                )
            ),
            "shadow_validation_performed": shadow["performed"],
            "shadow_full_is_feasible": shadow["full_is_feasible"],
            "shadow_false_rejection": shadow["false_rejection"],
            "shadow_process_calls": shadow["process_calls"],
            "shadow_op_calls": shadow["op_calls"],
            "shadow_ac_calls": shadow["ac_calls"],
            "shadow_transient_calls": shadow["transient_calls"],
            "shadow_accumulated_ngspice_seconds": shadow["accumulated_ngspice_seconds"],
            "shadow_outer_wall_seconds": shadow["outer_wall_seconds"],
            "shadow_analysis_errors": shadow["analysis_errors"],
            "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
            "task7_search_space_hash": TASK7_SEARCH_SPACE_HASH,
            "task9_protocol_hash": TASK9_PROTOCOL_HASH,
            "pvt_benchmark_hash": PVT_BENCHMARK_HASH,
            "corner_suite_hash": CORNER_SUITE_HASH,
            "corner_order_hash": CORNER_ORDER_HASH,
            "pvt_evaluation_policy_hash": PVT_EVALUATION_POLICY_HASH,
            "policy_hash": policy_hash(definition.policy),
            "partial_feedback_hash": PARTIAL_FEEDBACK_HASH,
            "simulation_time_budget_hash": SIMULATION_TIME_BUDGET_HASH,
            "cost_accounting_hash": COST_ACCOUNTING_HASH,
            "run_directory": (Path("runs") / f"evaluation_{iteration:04d}").as_posix(),
        }
        records.append(record)
        _save_records(run.path, records)
        metrics, objective, status = _optimizer_feedback(record)
        selected_optimizer.tell(parameters, metrics, objective, status)
        _save_optimizer_state(selected_optimizer, state_path)
        inflight_path.unlink()
        new_count += 1
    elapsed = elapsed_offset + monotonic() - started
    summary = _summary(definition, config, run.run_id, records, elapsed)
    _atomic_json(run.path / "summary" / "experiment_summary.json", summary)
    return run.path, summary
