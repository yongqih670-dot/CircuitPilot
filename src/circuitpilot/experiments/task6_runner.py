"""Resumable Task 6 optimizer loop with two independent cost axes."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from time import monotonic
from typing import Any

from circuitpilot.exceptions import (
    AnalysisError,
    CircuitPilotError,
    NetlistError,
    ParseError,
    ResearchExperimentError,
    SimulationError,
)
from circuitpilot.experiments.config import (
    ExperimentConfig,
    load_experiment_config,
    write_experiment_config,
)
from circuitpilot.experiments.optimizers.base import Optimizer
from circuitpilot.experiments.optimizers.factory import create_optimizer
from circuitpilot.experiments.seeding import SeedRegistry, initialize_seeds
from circuitpilot.experiments.task6_policy import (
    CandidateCostTracker,
    EvaluationPolicy,
    create_evaluation_policy,
)
from circuitpilot.experiments.task6_recorder import (
    Task6EvaluationRecord,
    Task6Recorder,
)
from circuitpilot.research_artifacts import write_research_manifest
from circuitpilot.run_directory import (
    ResearchRunDirectory,
    prepare_research_run_directory,
)
from circuitpilot.sky130_differential_amplifier import (
    Sky130DifferentialAmplifierCircuitConfig,
)
from circuitpilot.task6_protocol import (
    FULL_POLICY,
    METHODS,
    SCREENED_POLICY,
    TASK5_BENCHMARK_HASH,
    evaluation_policy_family_hash,
    evaluation_policy_hash,
    stable_hash,
)


TASK6_RUN_CONFIG_FILENAME = "task6_run_config.json"


@dataclass(frozen=True, slots=True)
class Task6RunDefinition:
    """One method-policy-seed cell in a frozen Task 6 design."""

    base_config_path: Path
    method: str
    evaluation_policy: str
    seed: int
    candidate_cap: int
    expensive_ac_budget: int | None
    experiment_design: str
    output_root: Path

    def __post_init__(self) -> None:
        if self.method not in METHODS:
            raise ValueError(f"unsupported Task 6 method '{self.method}'")
        if self.evaluation_policy not in {FULL_POLICY, SCREENED_POLICY}:
            raise ValueError("evaluation_policy must be full or op_screened")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a non-negative integer")
        if (
            isinstance(self.candidate_cap, bool)
            or not isinstance(self.candidate_cap, int)
            or self.candidate_cap <= 0
        ):
            raise ValueError("candidate_cap must be a positive integer")
        if self.expensive_ac_budget is not None and (
            isinstance(self.expensive_ac_budget, bool)
            or not isinstance(self.expensive_ac_budget, int)
            or self.expensive_ac_budget <= 0
            or self.expensive_ac_budget % 2
        ):
            raise ValueError("expensive_ac_budget must be a positive even integer or null")
        if self.experiment_design not in {
            "smoke",
            "formal_equal_candidate",
            "formal_equal_cost",
        }:
            raise ValueError("invalid Task 6 experiment design")

    @property
    def experiment_id(self) -> str:
        return (
            f"task6_{self.experiment_design}_{self.evaluation_policy}_"
            f"{self.method}_seed{self.seed}"
        )

    def semantic_dict(self) -> dict[str, Any]:
        """Return the resume/fairness identity, excluding filesystem placement."""
        return {
            "schema_version": 1,
            "experiment_id": self.experiment_id,
            "experiment_design": self.experiment_design,
            "method": self.method,
            "evaluation_policy": self.evaluation_policy,
            "seed": self.seed,
            "candidate_cap": self.candidate_cap,
            "expensive_ac_budget": self.expensive_ac_budget,
            "task5_benchmark_hash": TASK5_BENCHMARK_HASH,
            "evaluation_policy_hash": evaluation_policy_hash(
                self.evaluation_policy
            ),
            "task6_policy_family_hash": evaluation_policy_family_hash(),
        }

    def identity_sha256(self) -> str:
        return stable_hash(self.semantic_dict())

    def resolved_config(self) -> ExperimentConfig:
        """Derive one ordinary optimizer config from the untouched Task 5 file."""
        base = load_experiment_config(self.base_config_path)
        if base.computed_benchmark_hash() != TASK5_BENCHMARK_HASH:
            raise ResearchExperimentError("Task 5 frozen benchmark hash drifted")
        return replace(
            base,
            experiment_name=self.experiment_id,
            method=self.method,
            seed=self.seed,
            simulation_budget=self.candidate_cap,
            output_dir=self.output_root,
            experiment_phase=(
                "smoke" if self.experiment_design == "smoke" else "baseline"
            ),
            resume=False,
        )


@dataclass(frozen=True, slots=True)
class Task6RunResult:
    run_id: str
    output_directory: Path
    records: tuple[Task6EvaluationRecord, ...]
    best_record: Task6EvaluationRecord | None
    completed: bool
    elapsed_seconds: float
    seed_registry: SeedRegistry

    @property
    def cost_totals(self) -> dict[str, int]:
        return {
            "candidate_evaluations": len(self.records),
            "ngspice_process_calls": sum(
                row.ngspice_process_calls for row in self.records
            ),
            "dc_op_calls": sum(row.dc_op_calls for row in self.records),
            "differential_ac_calls": sum(
                row.differential_ac_calls for row in self.records
            ),
            "common_mode_ac_calls": sum(
                row.common_mode_ac_calls for row in self.records
            ),
            "full_ac_candidate_count": sum(
                row.full_ac_candidate_count for row in self.records
            ),
            "expensive_ac_analysis_count": sum(
                row.expensive_ac_analysis_count for row in self.records
            ),
            "physical_analysis_calls": sum(
                row.physical_analysis_calls for row in self.records
            ),
        }


def _failure_status(exc: Exception) -> str:
    if isinstance(exc, SimulationError):
        return "simulation_failed"
    if isinstance(exc, NetlistError):
        return "netlist_failed"
    if isinstance(exc, ParseError):
        return "parse_failed"
    if isinstance(exc, AnalysisError):
        return "analysis_failed"
    return "evaluation_failed"


def _atomic_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def _validate_resumed_records(
    definition: Task6RunDefinition,
    records: tuple[Task6EvaluationRecord, ...],
) -> None:
    expected_hash = evaluation_policy_hash(definition.evaluation_policy)
    family_hash = evaluation_policy_family_hash()
    cumulative_ac = 0
    event_seen = False
    for expected_iteration, record in enumerate(records, start=1):
        if record.iteration != expected_iteration:
            raise ResearchExperimentError(
                "resumed Task 6 iterations are not contiguous"
            )
        if (
            record.experiment_id != definition.experiment_id
            or record.method != definition.method
            or record.evaluation_policy != definition.evaluation_policy
            or record.seed != definition.seed
            or record.experiment_design != definition.experiment_design
            or record.task5_benchmark_hash != TASK5_BENCHMARK_HASH
            or record.evaluation_policy_hash != expected_hash
            or record.task6_policy_family_hash != family_hash
        ):
            raise ResearchExperimentError(
                "recorded evaluations do not match the Task 6 run identity"
            )
        cumulative_ac += record.expensive_ac_analysis_count
        if record.expensive_ac_calls_cumulative != cumulative_ac:
            raise ResearchExperimentError(
                "resumed Task 6 cumulative AC accounting is inconsistent"
            )
        if record.event_observed:
            if event_seen or not record.is_feasible:
                raise ResearchExperimentError(
                    "resumed Task 6 feasibility event is inconsistent"
                )
            event_seen = True


def _is_complete(
    definition: Task6RunDefinition,
    records: tuple[Task6EvaluationRecord, ...],
) -> bool:
    if len(records) >= definition.candidate_cap:
        return True
    return (
        definition.expensive_ac_budget is not None
        and sum(row.expensive_ac_analysis_count for row in records)
        >= definition.expensive_ac_budget
    )


def _best_record(
    records: tuple[Task6EvaluationRecord, ...],
) -> Task6EvaluationRecord | None:
    eligible = [
        row
        for row in records
        if row.evaluation_stage == "full_evaluated"
        and row.simulation_status == "success"
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


def _summary_payload(
    definition: Task6RunDefinition,
    result: Task6RunResult,
) -> dict[str, Any]:
    records = result.records
    first = next((row for row in records if row.event_observed), None)
    best = result.best_record
    totals = result.cost_totals
    failures = sum(row.simulation_status != "success" for row in records)
    rejected = sum(row.evaluation_stage == "op_rejected" for row in records)
    full = sum(row.evaluation_stage == "full_evaluated" for row in records)
    return {
        **definition.semantic_dict(),
        "run_id": result.run_id,
        "completed": result.completed,
        "evaluations_success": len(records) - failures,
        "evaluations_failed": failures,
        "op_rejected_candidates": rejected,
        "full_evaluated_candidates": full,
        "physics_invalid_candidates": sum(
            row.physics_status == "invalid" for row in records
        ),
        "feasible_candidates": sum(row.is_feasible for row in records),
        **totals,
        "total_runtime": result.elapsed_seconds,
        "event_observed": first is not None,
        "candidate_time_to_first_feasible": (
            None if first is None else first.iteration
        ),
        "expensive_ac_time_to_first_feasible": (
            None if first is None else first.expensive_ac_calls_cumulative
        ),
        "wall_time_to_first_feasible": (
            None if first is None else first.total_elapsed_time
        ),
        "candidate_censor_time": len(records),
        "expensive_ac_censor_time": totals["expensive_ac_analysis_count"],
        "wall_time_censor_time": result.elapsed_seconds,
        "best_result": (
            None
            if best is None
            else {
                "iteration": best.iteration,
                "parameters": best.parameters,
                "raw_metrics": best.raw_metrics,
                "objective_value": best.objective_value,
                "constraint_violation": best.constraint_violation,
                "is_feasible": best.is_feasible,
            }
        ),
    }


class Task6Runner:
    """Shared method-independent loop; policy is the sole experiment variable."""

    def __init__(
        self,
        *,
        definition: Task6RunDefinition,
        config: ExperimentConfig,
        run: ResearchRunDirectory,
        optimizer: Optimizer,
        policy: EvaluationPolicy,
        recorder: Task6Recorder,
        seed_registry: SeedRegistry,
        optimizer_state_path: Path,
    ) -> None:
        self.definition = definition
        self.config = config
        self.run = run
        self.optimizer = optimizer
        self.policy = policy
        self.recorder = recorder
        self.seed_registry = seed_registry
        self.optimizer_state_path = optimizer_state_path

    def run_to_budget(
        self, *, max_new_candidates: int | None = None
    ) -> Task6RunResult:
        started = monotonic()
        records = self.recorder.records()
        _validate_resumed_records(self.definition, records)
        elapsed_offset = records[-1].total_elapsed_time if records else 0.0
        expensive_ac_total = sum(
            row.expensive_ac_analysis_count for row in records
        )
        already_feasible = any(row.is_feasible for row in records)
        new_count = 0

        while not _is_complete(self.definition, records):
            if max_new_candidates is not None and new_count >= max_new_candidates:
                break
            parameters = self.optimizer.ask()
            optimizer_phase = self.optimizer.get_last_ask_metadata().get(
                "optimizer_phase", "search"
            )
            iteration = len(records) + 1
            run_name = f"evaluation_{iteration:04d}"
            evaluation_directory = self.run.path / "runs" / run_name
            evaluation_directory.mkdir(parents=True, exist_ok=True)
            portable_directory = (Path("runs") / run_name).as_posix()
            candidate_started = monotonic()
            cost = CandidateCostTracker()

            metrics: dict[str, float | None] = {}
            objective_value: float | None = None
            constraint_violation: float | None = None
            is_feasible = False
            simulation_status = "success"
            measurement_status: str | None = None
            evaluation_stage: str | None = None
            physics_status: str | None = None
            physics_violation_mask = 0
            physics_violation_count = 0
            physics_violation_types: tuple[str, ...] = ()
            op_constraint_violation: float | None = None
            bandwidth_status: str | None = None
            bandwidth_lower_bound_hz: float | None = None
            cmrr_status: str | None = None
            cmrr_lower_bound_db: float | None = None
            failure_type: str | None = None
            error_message: str | None = None
            policy_message: str | None = None

            try:
                self.config.validate_parameters(parameters)
                outcome = self.policy.evaluate(
                    parameters, evaluation_directory, cost
                )
                metrics = dict(outcome.metrics)
                objective_value = outcome.objective_value
                constraint_violation = outcome.constraint_violation
                is_feasible = outcome.is_feasible
                measurement_status = outcome.measurement_status
                evaluation_stage = outcome.evaluation_stage
                physics_status = outcome.physics.physics_status
                physics_violation_mask = outcome.physics.violation_mask
                physics_violation_count = outcome.physics.violation_count
                physics_violation_types = outcome.physics.violation_types
                op_constraint_violation = outcome.physics.op_constraint_violation
                bandwidth_status = outcome.bandwidth_status
                bandwidth_lower_bound_hz = outcome.bandwidth_lower_bound_hz
                cmrr_status = outcome.cmrr_status
                cmrr_lower_bound_db = outcome.cmrr_lower_bound_db
                policy_message = outcome.message
            except (CircuitPilotError, OSError, ValueError) as exc:
                postprocess_failure = (
                    cost.ngspice_process_calls > 0
                    and not isinstance(exc, SimulationError)
                )
                simulation_status = (
                    "success" if postprocess_failure else _failure_status(exc)
                )
                if postprocess_failure:
                    measurement_status = "analysis_error"
                failure_type = type(exc).__name__
                error_message = str(exc)
                (evaluation_directory / "evaluation_error.txt").write_text(
                    str(exc) + "\n", encoding="utf-8"
                )
                metrics = {}
                objective_value = None
                constraint_violation = None
                is_feasible = False

            optimizer_status = (
                "success"
                if simulation_status == "success" and objective_value is not None
                else (measurement_status or simulation_status)
            )
            optimizer_metrics = (
                {
                    name: value
                    for name, value in metrics.items()
                    if value is not None
                }
                if objective_value is not None
                else {}
            )
            self.optimizer.tell(
                parameters,
                optimizer_metrics,
                objective_value,
                optimizer_status,
            )

            expensive_ac_total += cost.expensive_ac_analysis_count
            candidate_elapsed = monotonic() - candidate_started
            total_elapsed = elapsed_offset + monotonic() - started
            event_observed = is_feasible and not already_feasible
            already_feasible = already_feasible or is_feasible
            record = Task6EvaluationRecord.now(
                experiment_id=self.definition.experiment_id,
                run_id=self.run.run_id,
                method=self.definition.method,
                evaluation_policy=self.definition.evaluation_policy,
                optimizer_phase=optimizer_phase,
                seed=self.definition.seed,
                iteration=iteration,
                parameters=dict(parameters),
                simulation_status=simulation_status,
                measurement_status=measurement_status,
                evaluation_stage=evaluation_stage,
                physics_status=physics_status,
                physics_violation_mask=physics_violation_mask,
                physics_violation_count=physics_violation_count,
                physics_violation_types=physics_violation_types,
                op_constraint_violation=op_constraint_violation,
                bandwidth_status=bandwidth_status,
                bandwidth_lower_bound_hz=bandwidth_lower_bound_hz,
                cmrr_status=cmrr_status,
                cmrr_lower_bound_db=cmrr_lower_bound_db,
                failure_type=failure_type,
                error_message=error_message,
                policy_message=policy_message,
                raw_metrics=metrics,
                objective_value=objective_value,
                constraint_violation=constraint_violation,
                is_feasible=is_feasible,
                candidate_evaluations=1,
                ngspice_process_calls=cost.ngspice_process_calls,
                dc_op_calls=cost.dc_op_calls,
                differential_ac_calls=cost.differential_ac_calls,
                common_mode_ac_calls=cost.common_mode_ac_calls,
                full_ac_candidate_count=cost.full_ac_candidate_count,
                expensive_ac_analysis_count=cost.expensive_ac_analysis_count,
                physical_analysis_calls=cost.physical_analysis_calls,
                expensive_ac_calls_cumulative=expensive_ac_total,
                wall_clock_seconds=candidate_elapsed,
                total_elapsed_time=total_elapsed,
                run_directory=portable_directory,
                task5_benchmark_hash=TASK5_BENCHMARK_HASH,
                evaluation_policy_hash=self.policy.policy_hash,
                task6_policy_family_hash=evaluation_policy_family_hash(),
                experiment_design=self.definition.experiment_design,
                event_observed=event_observed,
            )
            self.recorder.save(record)
            self.optimizer.save_state(self.optimizer_state_path)
            records = self.recorder.records()
            new_count += 1

        elapsed = elapsed_offset + monotonic() - started
        completed = _is_complete(self.definition, records)
        return Task6RunResult(
            run_id=self.run.run_id,
            output_directory=self.run.path,
            records=records,
            best_record=_best_record(records),
            completed=completed,
            elapsed_seconds=elapsed,
            seed_registry=self.seed_registry,
        )


def execute_task6_run(
    definition: Task6RunDefinition,
    *,
    resume_directory: str | Path | None = None,
    optimizer: Optimizer | None = None,
    policy: EvaluationPolicy | None = None,
    max_new_candidates: int | None = None,
) -> Task6RunResult:
    """Run or explicitly resume one Task 6 cell and seal it when complete."""
    config = definition.resolved_config()
    run = prepare_research_run_directory(
        resume_directory,
        resume=resume_directory is not None,
        default_root=definition.output_root,
        configuration_sha256=definition.identity_sha256(),
    )
    for directory in (run.path / "runs", run.path / "plots", run.path / "summary"):
        directory.mkdir(parents=True, exist_ok=True)

    task6_config_path = run.path / TASK6_RUN_CONFIG_FILENAME
    if run.resumed:
        try:
            original = json.loads(task6_config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ResearchExperimentError(
                f"cannot resume without valid {TASK6_RUN_CONFIG_FILENAME}: {exc}"
            ) from exc
        if original != definition.semantic_dict():
            raise ResearchExperimentError("resumed Task 6 definition changed")
    else:
        _atomic_json(task6_config_path, definition.semantic_dict())
        write_experiment_config(config, run.path / "experiment_config.yaml")

    seeds = initialize_seeds(definition.seed)
    recorder = Task6Recorder(run.path)
    existing = recorder.records()
    _validate_resumed_records(definition, existing)
    selected_optimizer = optimizer or create_optimizer(config, seeds)
    state_path = run.path / "summary" / "optimizer_state.json"
    if run.resumed and existing:
        if not state_path.is_file():
            raise ResearchExperimentError(
                "cannot resume Task 6 without optimizer state"
            )
        selected_optimizer.load_state(state_path)
    selected_policy = policy or create_evaluation_policy(
        definition.evaluation_policy, config
    )
    if (
        selected_policy.policy_name != definition.evaluation_policy
        or selected_policy.policy_hash
        != evaluation_policy_hash(definition.evaluation_policy)
    ):
        raise ResearchExperimentError("injected Task 6 policy identity mismatch")

    result = Task6Runner(
        definition=definition,
        config=config,
        run=run,
        optimizer=selected_optimizer,
        policy=selected_policy,
        recorder=recorder,
        seed_registry=seeds.registry,
        optimizer_state_path=state_path,
    ).run_to_budget(max_new_candidates=max_new_candidates)

    summary = _summary_payload(definition, result)
    _atomic_json(run.path / "summary" / "experiment_summary.json", summary)
    if not result.completed:
        return result

    best = result.best_record
    circuit = config.circuit_config
    model_metadata: dict[str, Any] | None = None
    if isinstance(circuit, Sky130DifferentialAmplifierCircuitConfig):
        model_metadata = circuit.model.metadata()
        model_metadata.update(
            {
                "topology_version": circuit.topology_version,
                "task6_policy_family_hash": evaluation_policy_family_hash(),
                "evaluation_policy_hash": evaluation_policy_hash(
                    definition.evaluation_policy
                ),
            }
        )
    write_research_manifest(
        result.output_directory,
        workflow="research_experiment",
        circuit_type=config.circuit_name,
        configuration={
            "task5": config.to_dict(),
            "task6": definition.semantic_dict(),
        },
        parameters={} if best is None else best.parameters,
        metrics=summary,
        runtime_seconds=result.elapsed_seconds,
        ngspice_executable=config.ngspice_config.executable,
        random_seed=config.seed,
        seed_registry=result.seed_registry.as_dict(),
        run_id=run.run_id,
        resumed=run.resumed,
        resume_count=run.resume_count,
        experiment_name=definition.experiment_id,
        benchmark_config_hash=TASK5_BENCHMARK_HASH,
        model_metadata=model_metadata,
    )
    return result
