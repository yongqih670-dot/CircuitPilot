"""Single optimizer-independent experiment loop and research-run orchestration."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from time import monotonic
from typing import Mapping

from circuitpilot.exceptions import (
    AnalysisError,
    CircuitPilotError,
    NetlistError,
    ParseError,
    ResearchExperimentError,
    SimulationError,
)
from circuitpilot.experiments.analyzer import (
    AnalysisOutcome,
    CandidateAnalyzer,
    CommonSourceAnalyzer,
    RCLowPassAnalyzer,
    Sky130CommonSourceAnalyzer,
)
from circuitpilot.experiments.budget import SimulationBudget
from circuitpilot.experiments.config import (
    ExperimentConfig,
    load_experiment_config,
    write_experiment_config,
)
from circuitpilot.experiments.objectives import ObjectiveEvaluator
from circuitpilot.experiments.optimizer import Optimizer, create_optimizer
from circuitpilot.experiments.recorder import EvaluationRecord, EvaluationRecorder
from circuitpilot.experiments.seeding import SeedRegistry, initialize_seeds
from circuitpilot.experiments.simulation import (
    CandidateSimulator,
    CommonSourceNgspiceSimulator,
    RCLowPassNgspiceSimulator,
    Sky130CommonSourceNgspiceSimulator,
)
from circuitpilot.sky130_common_source import Sky130CommonSourceCircuitConfig
from circuitpilot.research_artifacts import write_research_manifest
from circuitpilot.run_directory import (
    ResearchRunDirectory,
    prepare_research_run_directory,
)


@dataclass(frozen=True, slots=True)
class ExperimentRunResult:
    """Completed common-run statistics and best successful record."""

    run_id: str
    output_directory: Path
    records: tuple[EvaluationRecord, ...]
    best_record: EvaluationRecord | None
    budget: dict[str, int]
    elapsed_seconds: float
    seed_registry: SeedRegistry


def _failure_status(exc: Exception) -> str:
    """Map expected failure classes to stable research status values."""
    if isinstance(exc, SimulationError):
        return "simulation_failed"
    if isinstance(exc, NetlistError):
        return "netlist_failed"
    if isinstance(exc, ParseError):
        return "parse_failed"
    if isinstance(exc, AnalysisError):
        return "analysis_failed"
    return "evaluation_failed"


class ExperimentRunner:
    """Only loop allowed to connect optimizers to the CircuitPilot simulator."""

    def __init__(
        self,
        *,
        config: ExperimentConfig,
        run: ResearchRunDirectory,
        optimizer: Optimizer,
        simulator: CandidateSimulator,
        analyzer: CandidateAnalyzer,
        objective_evaluator: ObjectiveEvaluator,
        recorder: EvaluationRecorder,
        budget: SimulationBudget,
        seed_registry: SeedRegistry,
        optimizer_state_path: Path,
    ) -> None:
        """Inject every dependency without branching on optimizer type."""
        self.config = config
        self.run = run
        self.optimizer = optimizer
        self.simulator = simulator
        self.analyzer = analyzer
        self.objective_evaluator = objective_evaluator
        self.recorder = recorder
        self.budget = budget
        self.seed_registry = seed_registry
        self.optimizer_state_path = optimizer_state_path

    def run_to_budget(self) -> ExperimentRunResult:
        """Execute ask/evaluate/analyze/tell/record until budget exhaustion."""
        started = monotonic()
        previous_records = self.recorder.records()
        elapsed_offset = (
            previous_records[-1].total_elapsed_time if previous_records else 0.0
        )
        while not self.budget.exhausted:
            parameters = self.optimizer.ask()
            optimizer_phase = self.optimizer.get_last_ask_metadata().get(
                "optimizer_phase", "search"
            )
            iteration = self.budget.reserve()
            run_name = f"evaluation_{iteration:04d}"
            evaluation_directory = self.run.path / "runs" / run_name
            evaluation_directory.mkdir(parents=True, exist_ok=True)
            portable_directory = (Path("runs") / run_name).as_posix()
            candidate_started = monotonic()
            metrics: dict[str, float | None] = {}
            objective_value: float | None = None
            constraint_violation: float | None = None
            is_feasible = False
            simulation_status = "success"
            failure_type: str | None = None
            error_message: str | None = None
            ngspice_return_code: int | None = None
            timed_out = False
            measurement_status: str | None = None
            bandwidth_status: str | None = None
            bandwidth_lower_bound_hz: float | None = None
            ngspice_calls_before = self.budget.ngspice_calls

            try:
                self.config.validate_parameters(parameters)
            except ValueError as exc:
                simulation_status = "invalid_parameters"
                failure_type = type(exc).__name__
                error_message = str(exc)
                error_path = evaluation_directory / "validation_error.txt"
                error_path.write_text(str(exc) + "\n", encoding="utf-8")
            else:
                try:
                    simulation = self.simulator.evaluate(
                        parameters,
                        evaluation_directory,
                        self.budget.mark_ngspice_call,
                    )
                    extracted = self.analyzer.extract(simulation, parameters)
                    if isinstance(extracted, AnalysisOutcome):
                        metrics = extracted.metrics
                        measurement_status = extracted.measurement_status
                        bandwidth_status = extracted.bandwidth_status
                        bandwidth_lower_bound_hz = extracted.bandwidth_lower_bound_hz
                        if measurement_status == "complete":
                            objective = self.objective_evaluator.evaluate(
                                metrics,
                                bandwidth_status=bandwidth_status,
                                bandwidth_lower_bound_hz=bandwidth_lower_bound_hz,
                            )
                            objective_value = objective.objective_value
                            constraint_violation = objective.constraint_violation
                            is_feasible = objective.is_feasible
                        else:
                            failure_type = (
                                "InvalidResponse"
                                if measurement_status == "invalid_response"
                                else "AnalysisError"
                            )
                            error_message = extracted.message
                    else:
                        metrics = extracted
                        measurement_status = "complete"
                        objective = self.objective_evaluator.evaluate(metrics)
                        objective_value = objective.objective_value
                        constraint_violation = objective.constraint_violation
                        is_feasible = objective.is_feasible
                except (CircuitPilotError, OSError, ValueError) as exc:
                    task4_postprocess_failure = (
                        self.config.circuit_name == "sky130_common_source"
                        and self.budget.ngspice_calls > ngspice_calls_before
                        and not isinstance(exc, SimulationError)
                    )
                    simulation_status = (
                        "success" if task4_postprocess_failure else _failure_status(exc)
                    )
                    if task4_postprocess_failure:
                        measurement_status = "analysis_error"
                        bandwidth_status = "analysis_error"
                    failure_type = type(exc).__name__
                    error_message = str(exc)
                    if isinstance(exc, SimulationError):
                        ngspice_return_code = exc.returncode
                        timed_out = exc.timed_out
                    error_path = evaluation_directory / "evaluation_error.txt"
                    error_path.write_text(str(exc) + "\n", encoding="utf-8")
                    metrics = {}
                    objective_value = None
                    constraint_violation = None
                    is_feasible = False

            if simulation_status == "success":
                self.budget.mark_success()
            else:
                self.budget.mark_failure()
            ngspice_called = self.budget.ngspice_calls > ngspice_calls_before
            optimizer_status = (
                "success"
                if simulation_status == "success" and objective_value is not None
                else (measurement_status or simulation_status)
            )
            self.optimizer.tell(
                parameters,
                {name: value for name, value in metrics.items() if value is not None},
                objective_value,
                optimizer_status,
            )
            already_feasible = any(record.is_feasible for record in self.recorder.records())
            record = EvaluationRecord.now(
                experiment_id=self.config.experiment_name,
                run_id=self.run.run_id,
                circuit=self.config.circuit_name,
                method=self.config.method,
                seed=self.config.seed,
                iteration=iteration,
                parameters=parameters,
                simulation_status=simulation_status,
                failure_type=failure_type,
                raw_metrics=metrics,
                objective_value=objective_value,
                constraint_violation=constraint_violation,
                simulation_time=monotonic() - candidate_started,
                total_elapsed_time=elapsed_offset + monotonic() - started,
                run_directory=portable_directory,
                ngspice_called=ngspice_called,
                optimizer_phase=optimizer_phase,
                is_feasible=is_feasible,
                error_message=error_message,
                ngspice_return_code=ngspice_return_code,
                timed_out=timed_out,
                benchmark_config_hash=self.config.computed_benchmark_hash(),
                experiment_phase=self.config.experiment_phase,
                event_observed=is_feasible and not already_feasible,
                evaluation_time=iteration,
                measurement_status=measurement_status,
                bandwidth_status=bandwidth_status,
                bandwidth_lower_bound_hz=bandwidth_lower_bound_hz,
            )
            self.recorder.save(record)
            self.optimizer.save_state(self.optimizer_state_path)

        records = self.recorder.records()
        successful = [
            record
            for record in records
            if record.simulation_status == "success"
            and record.objective_value is not None
            and record.constraint_violation is not None
        ]
        best = (
            min(
                successful,
                key=lambda record: (
                    float(record.constraint_violation),
                    float(record.objective_value),
                    record.iteration,
                ),
            )
            if successful
            else None
        )
        return ExperimentRunResult(
            run_id=self.run.run_id,
            output_directory=self.run.path,
            records=records,
            best_record=best,
            budget=self.budget.as_dict(),
            elapsed_seconds=elapsed_offset + monotonic() - started,
            seed_registry=self.seed_registry,
        )


def _budget_from_records(
    config: ExperimentConfig, records: tuple[EvaluationRecord, ...]
) -> SimulationBudget:
    """Reconstruct exact budget counters for an explicit resume."""
    for expected_iteration, record in enumerate(records, start=1):
        if record.iteration != expected_iteration:
            raise ResearchExperimentError("resumed evaluation iterations are not contiguous")
        if (
            record.circuit != config.circuit_name
            or record.method != config.method
            or record.seed != config.seed
        ):
            raise ResearchExperimentError(
                "recorded evaluations do not match the resumed experiment config"
            )
    successful = sum(record.simulation_status == "success" for record in records)
    return SimulationBudget(
        limit=config.simulation_budget,
        evaluations_total=len(records),
        evaluations_success=successful,
        evaluations_failed=len(records) - successful,
        ngspice_calls=sum(record.ngspice_called for record in records),
    )


def _write_summary(config: ExperimentConfig, result: ExperimentRunResult) -> Path:
    """Write a deterministic machine-readable run summary."""
    destination = result.output_directory / "summary" / "experiment_summary.json"
    best = result.best_record
    feasible = [record for record in result.records if record.is_feasible]
    first_feasible = feasible[0] if feasible else None
    mean_simulation_time = (
        sum(record.simulation_time for record in result.records) / len(result.records)
        if result.records
        else 0.0
    )
    payload = {
        "run_id": result.run_id,
        "experiment_name": config.experiment_name,
        "circuit": config.circuit_name,
        "method": config.method,
        "seed": config.seed,
        "simulation_budget": config.simulation_budget,
        "evaluations_total": result.budget["evaluations_total"],
        "evaluations_success": result.budget["evaluations_success"],
        "evaluations_failed": result.budget["evaluations_failed"],
        "ngspice_calls": result.budget["ngspice_calls"],
        "budget": result.budget,
        "elapsed_seconds": result.elapsed_seconds,
        "total_runtime": result.elapsed_seconds,
        "mean_simulation_time": mean_simulation_time,
        "best_objective": None if best is None else best.objective_value,
        "best_parameters": None if best is None else best.parameters,
        "best_metrics": None if best is None else best.raw_metrics,
        "is_feasible": first_feasible is not None,
        "first_feasible_iteration": None if first_feasible is None else first_feasible.iteration,
        "simulations_to_first_feasible": None if first_feasible is None else first_feasible.iteration,
        "best_result": (
            None
            if best is None
            else {
                "iteration": best.iteration,
                "parameters": best.parameters,
                "raw_metrics": best.raw_metrics,
                "objective_value": best.objective_value,
                "constraint_violation": best.constraint_violation,
                "run_directory": best.run_directory,
            }
        ),
    }
    temporary = destination.with_name(f".{destination.name}.tmp")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
    except (OSError, TypeError, ValueError) as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ResearchExperimentError(
            f"failed to write experiment summary '{destination}': {exc}"
        ) from exc
    return destination


def _plot_progress(result: ExperimentRunResult) -> Path | None:
    """Plot measured objective progress without fabricating failed values."""
    successful = [
        record
        for record in result.records
        if record.simulation_status == "success" and record.objective_value is not None
    ]
    if not successful:
        return None
    import matplotlib.pyplot as plt

    destination = result.output_directory / "plots" / "objective_progress.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    indices = [record.iteration for record in successful]
    objectives = [float(record.objective_value) for record in successful]
    best_values: list[float] = []
    current = float("inf")
    for value in objectives:
        current = min(current, value)
        best_values.append(current)
    figure, axis = plt.subplots(figsize=(8, 5), constrained_layout=True)
    try:
        axis.plot(indices, objectives, marker="o", alpha=0.5, label="evaluation")
        axis.plot(indices, best_values, linewidth=2, label="best so far")
        axis.set_xlabel("Candidate evaluation")
        axis.set_ylabel("Minimized objective")
        axis.set_title("CircuitPilot Research Experiment")
        axis.grid(True, linestyle=":", alpha=0.6)
        axis.legend(loc="best")
        figure.savefig(destination, dpi=150)
    finally:
        plt.close(figure)
    return destination


def execute_experiment(
    config: ExperimentConfig,
    *,
    optimizer: Optimizer | None = None,
    simulator: CandidateSimulator | None = None,
    analyzer: CandidateAnalyzer | None = None,
    objective_evaluator: ObjectiveEvaluator | None = None,
) -> ExperimentRunResult:
    """Prepare one research directory, run the common loop, and seal artifacts."""
    run = prepare_research_run_directory(
        config.output_dir if config.resume else None,
        resume=config.resume,
        default_root=config.output_dir,
        configuration_sha256=config.resume_identity_sha256(),
    )
    resolved_config_path = run.path / "experiment_config.yaml"
    if run.resumed:
        if not resolved_config_path.is_file():
            raise ResearchExperimentError(
                "cannot resume research run without experiment_config.yaml"
            )
        original = load_experiment_config(resolved_config_path)
        if original.resume_identity_sha256() != config.resume_identity_sha256():
            raise ResearchExperimentError(
                "resumed experiment_config.yaml does not match current configuration"
            )
        if config.simulation_budget < original.simulation_budget:
            raise ResearchExperimentError("resume cannot reduce simulation_budget")
        write_experiment_config(config, resolved_config_path)
    else:
        write_experiment_config(config, resolved_config_path)
    for directory in (run.path / "runs", run.path / "plots", run.path / "summary"):
        directory.mkdir(parents=True, exist_ok=True)

    seeds = initialize_seeds(config.seed)
    recorder = EvaluationRecorder(run.path)
    existing_records = recorder.records()
    budget = _budget_from_records(config, existing_records)
    selected_optimizer = optimizer or create_optimizer(config, seeds)
    state_path = run.path / "summary" / "optimizer_state.json"
    if run.resumed and existing_records:
        if not state_path.is_file():
            raise ResearchExperimentError(
                "cannot resume evaluations without summary/optimizer_state.json"
            )
        selected_optimizer.load_state(state_path)

    if config.circuit_name == "rc_lowpass":
        selected_simulator = simulator or RCLowPassNgspiceSimulator(config)
        selected_analyzer = analyzer or RCLowPassAnalyzer(config)
    elif config.circuit_name == "common_source":
        selected_simulator = simulator or CommonSourceNgspiceSimulator(config)
        selected_analyzer = analyzer or CommonSourceAnalyzer(config)
    else:
        selected_simulator = simulator or Sky130CommonSourceNgspiceSimulator(config)
        selected_analyzer = analyzer or Sky130CommonSourceAnalyzer(config)

    runner = ExperimentRunner(
        config=config,
        run=run,
        optimizer=selected_optimizer,
        simulator=selected_simulator,
        analyzer=selected_analyzer,
        objective_evaluator=objective_evaluator or ObjectiveEvaluator(config),
        recorder=recorder,
        budget=budget,
        seed_registry=seeds.registry,
        optimizer_state_path=state_path,
    )
    result = runner.run_to_budget()
    _write_summary(config, result)
    _plot_progress(result)
    best = result.best_record
    manifest_metrics: dict[str, object] = {
        **({} if best is None else best.raw_metrics),
        "objective_value": None if best is None else best.objective_value,
        "constraint_violation": None if best is None else best.constraint_violation,
        "is_feasible": any(record.is_feasible for record in result.records),
        "first_feasible_iteration": next((record.iteration for record in result.records if record.is_feasible), None),
        **result.budget,
    }
    model_metadata = None
    if isinstance(config.circuit_config, Sky130CommonSourceCircuitConfig):
        model_metadata = config.circuit_config.model.metadata()
        model_metadata.update(
            {
                "bandwidth_semantics_version": config.circuit_config.bandwidth_semantics_version,
                "censoring_policy": config.circuit_config.censoring_policy,
                "difficulty_protocol_version": config.circuit_config.difficulty_protocol_version,
            }
        )
    elif config.circuit_config is not None:
        model = config.circuit_config.model
        model_metadata = {
            "model_path": str(model.require_library()),
            "model_library_sha256": model.library_sha256(),
            "model_name": model.model_name,
            "model_section": model.model_section,
            "corner": model.corner,
            "device_kind": model.device_kind,
            "provenance": model.provenance,
        }
    write_research_manifest(
        result.output_directory,
        workflow="research_experiment",
        circuit_type=config.circuit_name,
        configuration=config.to_dict(),
        parameters={} if best is None else best.parameters,
        metrics=manifest_metrics,
        runtime_seconds=result.elapsed_seconds,
        ngspice_executable=config.ngspice_config.executable,
        random_seed=config.seed,
        seed_registry=result.seed_registry.as_dict(),
        run_id=run.run_id,
        resumed=run.resumed,
        resume_count=run.resume_count,
        experiment_name=config.experiment_name,
        benchmark_config_hash=config.computed_benchmark_hash(),
        model_metadata=model_metadata,
    )
    return result
