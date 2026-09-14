"""Task 6 Full and operating-point-screened evaluation policies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from circuitpilot.experiments.analyzer import (
    AnalysisOutcome,
    Sky130DifferentialAmplifierAnalyzer,
)
from circuitpilot.experiments.config import ExperimentConfig
from circuitpilot.experiments.objectives import ObjectiveEvaluator
from circuitpilot.experiments.simulation import (
    CandidateSimulation,
    Sky130DifferentialAmplifierNgspiceSimulator,
)
from circuitpilot.sky130_differential_amplifier import (
    DifferentialOperatingPoint,
    Sky130DifferentialAmplifierCircuitConfig,
)
from circuitpilot.task6_physics import (
    PhysicsAssessment,
    REJECTED_OBJECTIVE_BASE,
    classify_task6_physics,
    rejected_policy_objective,
    run_task6_ac_only,
    run_task6_op_only,
    task6_operating_point_metrics,
)
from circuitpilot.task6_protocol import (
    FULL_POLICY,
    SCREENED_POLICY,
    evaluation_policy_hash,
)


@dataclass(slots=True)
class CandidateCostTracker:
    """Count attempted processes and analyses at their launch boundary."""

    ngspice_process_calls: int = 0
    dc_op_calls: int = 0
    differential_ac_calls: int = 0
    common_mode_ac_calls: int = 0
    full_ac_candidate_count: int = 0
    physical_analysis_calls: int = 0

    def mark_full_process(self) -> None:
        self.ngspice_process_calls += 1
        self.dc_op_calls += 1
        self.differential_ac_calls += 1
        self.common_mode_ac_calls += 1
        self.full_ac_candidate_count += 1
        self.physical_analysis_calls += 2

    def mark_op_process(self) -> None:
        self.ngspice_process_calls += 1
        self.dc_op_calls += 1
        self.physical_analysis_calls += 1

    def mark_ac_process(self) -> None:
        self.ngspice_process_calls += 1
        self.differential_ac_calls += 1
        self.common_mode_ac_calls += 1
        self.full_ac_candidate_count += 1
        self.physical_analysis_calls += 1

    @property
    def expensive_ac_analysis_count(self) -> int:
        return self.differential_ac_calls + self.common_mode_ac_calls


@dataclass(frozen=True, slots=True)
class Task6PolicyOutcome:
    """One policy result with physical, optimizer, stage, and cost semantics."""

    metrics: dict[str, float | None]
    objective_value: float | None
    constraint_violation: float | None
    is_feasible: bool
    measurement_status: str
    bandwidth_status: str | None
    bandwidth_lower_bound_hz: float | None
    cmrr_status: str | None
    cmrr_lower_bound_db: float | None
    evaluation_stage: str
    physics: PhysicsAssessment
    message: str | None = None


class EvaluationPolicy(Protocol):
    """The only Task 6 experiment variable."""

    policy_name: str
    policy_hash: str

    def evaluate(
        self,
        parameters: Mapping[str, float | int],
        evaluation_directory: Path,
        cost: CandidateCostTracker,
    ) -> Task6PolicyOutcome:
        """Return real evidence and optimizer feedback for one candidate."""


class _BasePolicy:
    def __init__(self, config: ExperimentConfig) -> None:
        if (
            config.circuit_name != "sky130_differential_amplifier"
            or not isinstance(
                config.circuit_config, Sky130DifferentialAmplifierCircuitConfig
            )
        ):
            raise ValueError("Task 6 policies require the Task 5 circuit")
        self.config = config
        self.circuit = config.circuit_config
        self.analyzer = Sky130DifferentialAmplifierAnalyzer(config)
        self.objective = ObjectiveEvaluator(config)

    def _full_outcome(
        self,
        simulation: CandidateSimulation,
        parameters: Mapping[str, float | int],
        physics: PhysicsAssessment,
    ) -> Task6PolicyOutcome:
        extracted = self.analyzer.extract(simulation, parameters)
        if not isinstance(extracted, AnalysisOutcome):
            raise TypeError("Task 6 requires structured Task 5 analysis")
        objective_value = None
        constraint_violation = None
        is_feasible = False
        if extracted.measurement_status == "complete":
            evaluated = self.objective.evaluate(
                extracted.metrics,
                bandwidth_status=extracted.bandwidth_status,
                bandwidth_lower_bound_hz=extracted.bandwidth_lower_bound_hz,
                cmrr_status=extracted.cmrr_status,
                cmrr_lower_bound_db=extracted.cmrr_lower_bound_db,
            )
            objective_value = evaluated.objective_value
            constraint_violation = evaluated.constraint_violation
            is_feasible = evaluated.is_feasible
            if objective_value >= REJECTED_OBJECTIVE_BASE:
                raise ValueError(
                    "Task 5 full objective violates the frozen Task 6 hierarchy"
                )
        return Task6PolicyOutcome(
            metrics=dict(extracted.metrics),
            objective_value=objective_value,
            constraint_violation=constraint_violation,
            is_feasible=is_feasible,
            measurement_status=extracted.measurement_status,
            bandwidth_status=extracted.bandwidth_status,
            bandwidth_lower_bound_hz=extracted.bandwidth_lower_bound_hz,
            cmrr_status=extracted.cmrr_status,
            cmrr_lower_bound_db=extracted.cmrr_lower_bound_db,
            evaluation_stage="full_evaluated",
            physics=physics,
            message=extracted.message,
        )


class FullEvaluationPolicy(_BasePolicy):
    """Run the unchanged Task 5 one-process OP plus combined dual AC path."""

    policy_name = FULL_POLICY
    policy_hash = evaluation_policy_hash(FULL_POLICY)

    def __init__(self, config: ExperimentConfig) -> None:
        super().__init__(config)
        self.simulator = Sky130DifferentialAmplifierNgspiceSimulator(config)

    def evaluate(
        self,
        parameters: Mapping[str, float | int],
        evaluation_directory: Path,
        cost: CandidateCostTracker,
    ) -> Task6PolicyOutcome:
        simulation = self.simulator.evaluate(
            parameters,
            evaluation_directory / "full",
            cost.mark_full_process,
        )
        operating_point = simulation.operating_point
        if not isinstance(operating_point, DifferentialOperatingPoint):
            raise ValueError("Task 5 Full simulation did not return a real OP")
        physics = classify_task6_physics(operating_point)
        return self._full_outcome(simulation, parameters, physics)


class OperatingPointScreeningPolicy(_BasePolicy):
    """Run OP first and conditionally launch the expensive dual-AC process."""

    policy_name = SCREENED_POLICY
    policy_hash = evaluation_policy_hash(SCREENED_POLICY)

    def evaluate(
        self,
        parameters: Mapping[str, float | int],
        evaluation_directory: Path,
        cost: CandidateCostTracker,
    ) -> Task6PolicyOutcome:
        op_only = run_task6_op_only(
            self.circuit,
            parameters,
            evaluation_directory / "op_stage",
            executable=self.config.ngspice_config.executable,
            timeout_seconds=self.config.timeout,
            on_ngspice_launch=cost.mark_op_process,
        )
        physics = classify_task6_physics(op_only.operating_point)
        if physics.physics_status == "invalid":
            metrics = task6_operating_point_metrics(op_only.operating_point)
            return Task6PolicyOutcome(
                metrics=metrics,
                objective_value=rejected_policy_objective(
                    physics.op_constraint_violation
                ),
                constraint_violation=physics.op_constraint_violation,
                is_feasible=False,
                measurement_status="op_only_complete",
                bandwidth_status=None,
                bandwidth_lower_bound_hz=None,
                cmrr_status=None,
                cmrr_lower_bound_db=None,
                evaluation_stage="op_rejected",
                physics=physics,
                message="AC skipped by frozen operating-point physics rules",
            )

        ac_only = run_task6_ac_only(
            self.circuit,
            parameters,
            evaluation_directory / "ac_stage",
            start_frequency_hz=self.config.ngspice_config.start_frequency_hz,
            stop_frequency_hz=self.config.ngspice_config.stop_frequency_hz,
            points_per_decade=self.config.ngspice_config.points_per_decade,
            executable=self.config.ngspice_config.executable,
            timeout_seconds=self.config.timeout,
            on_ngspice_launch=cost.mark_ac_process,
        )
        simulation = CandidateSimulation(
            response=ac_only.differential_response,
            common_mode_response=ac_only.common_mode_response,
            process=ac_only.process,
            netlist_path=ac_only.netlist_path,
            data_path=ac_only.differential_path,
            common_mode_data_path=ac_only.common_mode_path,
            log_path=ac_only.log_path,
            operating_point=op_only.operating_point,
            dc_data_path=op_only.op_path,
            device_op_data_path=op_only.device_op_path,
            ngspice_process_calls=cost.ngspice_process_calls,
            analysis_calls=cost.physical_analysis_calls,
        )
        return self._full_outcome(simulation, parameters, physics)


def create_evaluation_policy(
    policy: str, config: ExperimentConfig
) -> EvaluationPolicy:
    if policy == FULL_POLICY:
        return FullEvaluationPolicy(config)
    if policy == SCREENED_POLICY:
        return OperatingPointScreeningPolicy(config)
    raise ValueError("evaluation policy must be full or op_screened")
