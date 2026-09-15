"""Resumable Full-only optimizer loop for Research Task 7."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from time import monotonic
from typing import Any

from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.experiments.config import (
    ExperimentConfig,
    load_experiment_config,
    write_experiment_config,
)
from circuitpilot.experiments.optimizers.base import Optimizer
from circuitpilot.experiments.optimizers.factory import create_optimizer
from circuitpilot.experiments.seeding import SeedRegistry, initialize_seeds
from circuitpilot.experiments.task7_recorder import (
    Task7EvaluationRecord,
    Task7Recorder,
)
from circuitpilot.research_artifacts import write_research_manifest
from circuitpilot.run_directory import ResearchRunDirectory, prepare_research_run_directory
from circuitpilot.sky130_two_stage_ota import (
    Sky130TwoStageOtaCircuitConfig,
    evaluate_task7_full_candidate,
)
from circuitpilot.task7_protocol import (
    METHODS,
    TASK7_BENCHMARK_HASH,
    TASK7_SEARCH_SPACE_HASH,
    Task7Specification,
    evaluate_task7_objective,
    protocol_family_hash,
    stable_hash,
    task7_component_hashes,
)


TASK7_RUN_CONFIG_FILENAME = "task7_run_config.json"
FROZEN_SPECIFICATION = Task7Specification(
    gain_min_db=12.0,
    ugf_min_hz=5.0e5,
    phase_margin_min_deg=35.0,
    power_max_w=1.5e-3,
    positive_slew_min_v_per_s=5.0e5,
    negative_slew_min_v_per_s=5.0e5,
    output_min_v=0.10,
    output_max_v=1.70,
)


@dataclass(frozen=True, slots=True)
class Task7RunDefinition:
    base_config_path: Path
    method: str
    seed: int
    candidate_budget: int
    experiment_design: str
    output_root: Path

    def __post_init__(self) -> None:
        if self.method not in METHODS:
            raise ValueError(f"unsupported Task 7 method '{self.method}'")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("Task 7 seed must be a non-negative integer")
        if (
            isinstance(self.candidate_budget, bool)
            or not isinstance(self.candidate_budget, int)
            or self.candidate_budget <= 0
        ):
            raise ValueError("Task 7 candidate budget must be positive")
        if self.experiment_design not in {"smoke", "formal"}:
            raise ValueError("Task 7 experiment design must be smoke or formal")

    @property
    def experiment_id(self) -> str:
        return f"task7_{self.experiment_design}_{self.method}_seed{self.seed}"

    def semantic_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "experiment_id": self.experiment_id,
            "experiment_design": self.experiment_design,
            "method": self.method,
            "seed": self.seed,
            "candidate_budget": self.candidate_budget,
            "evaluation_policy": "full_only",
            "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
            "task7_search_space_hash": TASK7_SEARCH_SPACE_HASH,
            "task7_protocol_family_hash": protocol_family_hash(),
        }

    def identity_sha256(self) -> str:
        return stable_hash(self.semantic_dict())

    def resolved_config(self) -> ExperimentConfig:
        config = load_experiment_config(self.base_config_path)
        if config.computed_benchmark_hash() != TASK7_BENCHMARK_HASH:
            raise ResearchExperimentError("Task 7 frozen benchmark hash drifted")
        if config.search_space_sha256() != TASK7_SEARCH_SPACE_HASH:
            raise ResearchExperimentError("Task 7 frozen search-space hash drifted")
        return replace(
            config,
            experiment_name=self.experiment_id,
            method=self.method,
            seed=self.seed,
            simulation_budget=self.candidate_budget,
            output_dir=self.output_root,
            experiment_phase=(
                "smoke" if self.experiment_design == "smoke" else "baseline"
            ),
            resume=False,
        )


@dataclass(frozen=True, slots=True)
class Task7RunResult:
    run_id: str
    output_directory: Path
    records: tuple[Task7EvaluationRecord, ...]
    best_record: Task7EvaluationRecord | None
    completed: bool
    elapsed_seconds: float
    seed_registry: SeedRegistry

    @property
    def cost_totals(self) -> dict[str, int]:
        fields = (
            "candidate_evaluations",
            "ngspice_process_calls",
            "op_calls",
            "ac_calls",
            "transient_calls",
            "high_fidelity_analysis_calls",
            "screening_calls",
        )
        return {
            name: sum(int(getattr(row, name)) for row in self.records)
            for name in fields
        }


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _best_record(
    records: tuple[Task7EvaluationRecord, ...],
) -> Task7EvaluationRecord | None:
    eligible = [
        row
        for row in records
        if row.simulation_status == "success"
        and row.objective_value is not None
        and row.constraint_violation is not None
    ]
    return (
        min(
            eligible,
            key=lambda row: (
                float(row.constraint_violation),
                float(row.objective_value),
                row.iteration,
            ),
        )
        if eligible
        else None
    )


def _validate_records(
    definition: Task7RunDefinition,
    records: tuple[Task7EvaluationRecord, ...],
) -> None:
    family = protocol_family_hash()
    event_seen = False
    for iteration, record in enumerate(records, start=1):
        if record.iteration != iteration:
            raise ResearchExperimentError("Task 7 iterations are not contiguous")
        if (
            record.experiment_id != definition.experiment_id
            or record.experiment_design != definition.experiment_design
            or record.method != definition.method
            or record.seed != definition.seed
            or record.task7_benchmark_hash != TASK7_BENCHMARK_HASH
            or record.task7_search_space_hash != TASK7_SEARCH_SPACE_HASH
            or record.task7_protocol_family_hash != family
        ):
            raise ResearchExperimentError("Task 7 resumed record identity changed")
        if (
            record.candidate_evaluations_cumulative != iteration
            or record.ngspice_process_calls_cumulative != 3 * iteration
            or record.op_calls_cumulative != iteration
            or record.ac_calls_cumulative != iteration
            or record.transient_calls_cumulative != iteration
            or record.high_fidelity_analysis_calls_cumulative != 3 * iteration
            or record.screening_calls_cumulative != 0
        ):
            raise ResearchExperimentError("Task 7 cumulative cost identity failed")
        if record.event_observed:
            if event_seen or not record.is_feasible:
                raise ResearchExperimentError("Task 7 feasibility event is inconsistent")
            event_seen = True


def _restore_optimizer(
    optimizer: Optimizer,
    records: tuple[Task7EvaluationRecord, ...],
    state_path: Path,
) -> None:
    optimizer.load_state(state_path)
    history_count = len(optimizer.get_history())
    if history_count > len(records):
        raise ResearchExperimentError("Task 7 optimizer checkpoint is ahead of records")
    for record in records[history_count:]:
        candidate = optimizer.ask()
        if candidate != record.parameters:
            raise ResearchExperimentError("Task 7 optimizer replay candidate drifted")
        metrics = (
            {
                name: float(value)
                for name, value in record.metrics.items()
                if value is not None
            }
            if record.simulation_status == "success"
            else {}
        )
        optimizer.tell(
            record.parameters,
            metrics,
            record.objective_value,
            record.simulation_status,
        )
    if history_count < len(records):
        optimizer.save_state(state_path)


class Task7Runner:
    """One method-neutral loop; every candidate calls the same Full evaluator."""

    def __init__(
        self,
        *,
        definition: Task7RunDefinition,
        config: ExperimentConfig,
        run: ResearchRunDirectory,
        optimizer: Optimizer,
        recorder: Task7Recorder,
        seed_registry: SeedRegistry,
        optimizer_state_path: Path,
    ) -> None:
        self.definition = definition
        self.config = config
        self.run = run
        self.optimizer = optimizer
        self.recorder = recorder
        self.seed_registry = seed_registry
        self.optimizer_state_path = optimizer_state_path

    def run_to_budget(
        self, *, max_new_candidates: int | None = None
    ) -> Task7RunResult:
        records = self.recorder.records()
        _validate_records(self.definition, records)
        elapsed_offset = records[-1].total_elapsed_time if records else 0.0
        started = monotonic()
        event_seen = any(row.is_feasible for row in records)
        new_count = 0
        circuit = self.config.circuit_config
        if not isinstance(circuit, Sky130TwoStageOtaCircuitConfig):
            raise ResearchExperimentError("Task 7 runner requires typed OTA config")

        while len(records) < self.definition.candidate_budget:
            if max_new_candidates is not None and new_count >= max_new_candidates:
                break
            parameters = self.optimizer.ask()
            self.config.validate_parameters(parameters)
            optimizer_phase = self.optimizer.get_last_ask_metadata().get(
                "optimizer_phase", "search"
            )
            iteration = len(records) + 1
            run_name = f"evaluation_{iteration:04d}"
            evaluation_directory = self.run.path / "runs" / run_name
            evaluation = evaluate_task7_full_candidate(
                circuit,
                parameters,
                evaluation_directory,
                executable=self.config.ngspice_config.executable,
                timeout_seconds=self.config.timeout,
                start_frequency_hz=self.config.ngspice_config.start_frequency_hz,
                stop_frequency_hz=self.config.ngspice_config.stop_frequency_hz,
                points_per_decade=self.config.ngspice_config.points_per_decade,
            )
            errors = dict(evaluation.errors)
            objective_value: float | None = None
            constraint_violation: float | None = None
            constraint_components: dict[str, float] = {}
            is_feasible = False
            if not any(errors.values()):
                try:
                    objective = evaluate_task7_objective(
                        evaluation.metrics,
                        FROZEN_SPECIFICATION,
                        ugf_status=evaluation.stability.ugf_status.value,
                        phase_margin_status=(
                            evaluation.stability.phase_margin_status.value
                        ),
                        positive_slew_status=evaluation.slew.positive_status.value,
                        negative_slew_status=evaluation.slew.negative_status.value,
                    )
                    objective_value = objective.objective_value
                    constraint_violation = objective.constraint_violation
                    constraint_components = dict(objective.constraint_components)
                    is_feasible = objective.is_feasible
                except (TypeError, ValueError) as exc:
                    errors["postprocess"] = f"{type(exc).__name__}: {exc}"
            simulation_status = (
                "success" if objective_value is not None else "analysis_failed"
            )
            optimizer_metrics = (
                {
                    name: float(value)
                    for name, value in evaluation.metrics.items()
                    if value is not None
                }
                if simulation_status == "success"
                else {}
            )
            self.optimizer.tell(
                parameters,
                optimizer_metrics,
                objective_value,
                simulation_status,
            )
            event_observed = is_feasible and not event_seen
            event_seen = event_seen or is_feasible
            total_elapsed = elapsed_offset + monotonic() - started
            region = evaluation.operating_region
            op = evaluation.operating_point
            record = Task7EvaluationRecord.now(
                experiment_id=self.definition.experiment_id,
                run_id=self.run.run_id,
                experiment_design=self.definition.experiment_design,
                method=self.definition.method,
                optimizer_phase=optimizer_phase,
                seed=self.definition.seed,
                iteration=iteration,
                parameters=dict(parameters),
                simulation_status=simulation_status,
                metrics=dict(evaluation.metrics),
                ugf_status=evaluation.stability.ugf_status.value,
                phase_margin_status=evaluation.stability.phase_margin_status.value,
                ugf_crossing_count=evaluation.stability.crossing_count,
                positive_slew_status=evaluation.slew.positive_status.value,
                negative_slew_status=evaluation.slew.negative_status.value,
                operating_region_valid=None if region is None else region.valid,
                operating_region_mask=0 if region is None else region.violation_mask,
                operating_region_types=(
                    () if region is None else region.violation_types
                ),
                device_status={} if region is None else dict(region.device_status),
                device_quantities=(
                    {}
                    if op is None
                    else {
                        role: dict(values)
                        for role, values in op.device_quantities.items()
                    }
                ),
                analysis_errors=errors,
                objective_value=objective_value,
                constraint_violation=constraint_violation,
                constraint_components=constraint_components,
                is_feasible=is_feasible,
                event_observed=event_observed,
                candidate_evaluations=evaluation.cost.candidate_evaluations,
                ngspice_process_calls=evaluation.cost.ngspice_process_calls,
                op_calls=evaluation.cost.op_calls,
                ac_calls=evaluation.cost.ac_calls,
                transient_calls=evaluation.cost.transient_calls,
                high_fidelity_analysis_calls=(
                    evaluation.cost.high_fidelity_analysis_calls
                ),
                screening_calls=0,
                op_runtime_seconds=evaluation.cost.op_runtime_seconds,
                ac_runtime_seconds=evaluation.cost.ac_runtime_seconds,
                transient_runtime_seconds=evaluation.cost.transient_runtime_seconds,
                wall_clock_seconds=evaluation.cost.wall_clock_seconds,
                total_elapsed_time=total_elapsed,
                candidate_evaluations_cumulative=iteration,
                ngspice_process_calls_cumulative=3 * iteration,
                op_calls_cumulative=iteration,
                ac_calls_cumulative=iteration,
                transient_calls_cumulative=iteration,
                high_fidelity_analysis_calls_cumulative=3 * iteration,
                screening_calls_cumulative=0,
                run_directory=(Path("runs") / run_name).as_posix(),
                task7_benchmark_hash=TASK7_BENCHMARK_HASH,
                task7_search_space_hash=TASK7_SEARCH_SPACE_HASH,
                task7_protocol_family_hash=protocol_family_hash(),
            )
            self.recorder.save(record)
            self.optimizer.save_state(self.optimizer_state_path)
            records = self.recorder.records()
            new_count += 1

        elapsed = elapsed_offset + monotonic() - started
        return Task7RunResult(
            run_id=self.run.run_id,
            output_directory=self.run.path,
            records=records,
            best_record=_best_record(records),
            completed=len(records) >= self.definition.candidate_budget,
            elapsed_seconds=elapsed,
            seed_registry=self.seed_registry,
        )


def _summary(
    definition: Task7RunDefinition,
    result: Task7RunResult,
    config: ExperimentConfig,
) -> dict[str, Any]:
    records = result.records
    first = next((row for row in records if row.event_observed), None)
    best = result.best_record
    return {
        **definition.semantic_dict(),
        "component_hashes": task7_component_hashes(config),
        "run_id": result.run_id,
        "completed": result.completed,
        "evaluations_success": sum(
            row.simulation_status == "success" for row in records
        ),
        "evaluations_failed": sum(
            row.simulation_status != "success" for row in records
        ),
        "feasible_candidates": sum(row.is_feasible for row in records),
        **result.cost_totals,
        "total_runtime": result.elapsed_seconds,
        "event_observed": first is not None,
        "candidate_time_to_first_feasible": (
            None if first is None else first.iteration
        ),
        "candidate_censor_time": len(records),
        "wall_time_to_first_feasible": (
            None if first is None else first.total_elapsed_time
        ),
        "best_result": (
            None
            if best is None
            else {
                "iteration": best.iteration,
                "parameters": best.parameters,
                "metrics": best.metrics,
                "objective_value": best.objective_value,
                "constraint_violation": best.constraint_violation,
                "is_feasible": best.is_feasible,
            }
        ),
    }


def execute_task7_run(
    definition: Task7RunDefinition,
    *,
    resume_directory: str | Path | None = None,
    optimizer: Optimizer | None = None,
    max_new_candidates: int | None = None,
) -> Task7RunResult:
    config = definition.resolved_config()
    run = prepare_research_run_directory(
        resume_directory,
        resume=resume_directory is not None,
        default_root=definition.output_root,
        configuration_sha256=definition.identity_sha256(),
    )
    for directory in (run.path / "runs", run.path / "plots", run.path / "summary"):
        directory.mkdir(parents=True, exist_ok=True)
    definition_path = run.path / TASK7_RUN_CONFIG_FILENAME
    if run.resumed:
        try:
            original = json.loads(definition_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ResearchExperimentError(f"invalid resumed Task 7 definition: {exc}") from exc
        if original != definition.semantic_dict():
            raise ResearchExperimentError("resumed Task 7 definition changed")
    else:
        _atomic_json(definition_path, definition.semantic_dict())
        write_experiment_config(config, run.path / "experiment_config.yaml")

    seeds = initialize_seeds(definition.seed)
    recorder = Task7Recorder(run.path)
    existing = recorder.records()
    _validate_records(definition, existing)
    selected_optimizer = optimizer or create_optimizer(config, seeds)
    state_path = run.path / "summary" / "optimizer_state.json"
    if run.resumed and existing:
        if not state_path.is_file():
            raise ResearchExperimentError("cannot resume Task 7 without optimizer state")
        _restore_optimizer(selected_optimizer, existing, state_path)

    result = Task7Runner(
        definition=definition,
        config=config,
        run=run,
        optimizer=selected_optimizer,
        recorder=recorder,
        seed_registry=seeds.registry,
        optimizer_state_path=state_path,
    ).run_to_budget(max_new_candidates=max_new_candidates)
    summary = _summary(definition, result, config)
    _atomic_json(run.path / "summary" / "experiment_summary.json", summary)
    if result.completed:
        circuit = config.circuit_config
        model_metadata = None
        if isinstance(circuit, Sky130TwoStageOtaCircuitConfig):
            model_metadata = circuit.model.metadata()
            model_metadata.update(
                {
                    "topology_version": circuit.topology_version,
                    "task7_protocol_family_hash": protocol_family_hash(),
                }
            )
        write_research_manifest(
            result.output_directory,
            workflow="research_experiment",
            circuit_type=config.circuit_name,
            configuration={
                "task7": definition.semantic_dict(),
                "benchmark": config.to_dict(),
            },
            parameters={} if result.best_record is None else result.best_record.parameters,
            metrics=summary,
            runtime_seconds=result.elapsed_seconds,
            ngspice_executable=config.ngspice_config.executable,
            random_seed=config.seed,
            seed_registry=result.seed_registry.as_dict(),
            run_id=run.run_id,
            resumed=run.resumed,
            resume_count=run.resume_count,
            experiment_name=definition.experiment_id,
            benchmark_config_hash=TASK7_BENCHMARK_HASH,
            model_metadata=model_metadata,
        )
    return result
