"""Resumable Full and hierarchical real-SKY130 evaluators for Task 8."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Mapping

from circuitpilot.parser import parse_ac_output
from circuitpilot.simulator import run_ngspice
from circuitpilot.sky130_common_source import sky130_runtime_paths
from circuitpilot.sky130_two_stage_ota import (
    PhaseMarginStatus,
    Sky130TwoStageOtaCircuitConfig,
    SlewStatus,
    UgfStatus,
    assess_task7_operating_regions,
    generate_task7_ac_netlist,
    generate_task7_op_netlist,
    generate_task7_transient_netlist,
    measure_task7_slew,
    measure_task7_stability,
    optional_minus_3db_bandwidth,
    parse_task7_operating_point,
    parse_task7_transient,
)
from circuitpilot.task7_protocol import evaluate_task7_objective
from circuitpilot.task8_protocol import (
    CANONICAL_METRICS,
    TASK8_SPECIFICATION,
    ac_gate,
    hierarchical_objective,
    op_gate,
    transient_gate,
)


CHECKPOINT_FILENAME = "stage_checkpoint.json"


class StageBoundaryReached(RuntimeError):
    """Test-only interruption emitted after a durable stage checkpoint."""


@dataclass(frozen=True, slots=True)
class StageMeasurement:
    kind: str
    metrics: dict[str, float | None]
    statuses: dict[str, Any]
    evidence: dict[str, Any]
    error: str | None
    process_elapsed_seconds: float
    outer_elapsed_seconds: float
    process_elapsed_estimated: bool = False


@dataclass(frozen=True, slots=True)
class Task8Evaluation:
    policy: str
    evaluation_stage: str
    first_blocking_constraint: str | None
    simulation_status: str
    metrics: dict[str, float | None]
    statuses: dict[str, Any]
    evidence: dict[str, Any]
    analysis_errors: dict[str, str | None]
    objective_value: float | None
    constraint_violation: float | None
    constraint_components: dict[str, float]
    is_feasible: bool
    ngspice_process_calls: int
    op_calls: int
    ac_calls: int
    transient_calls: int
    accumulated_ngspice_seconds: float
    outer_wall_seconds: float
    orchestration_seconds: float
    process_elapsed_estimate_count: int

    @property
    def logical_high_fidelity_calls(self) -> int:
        return self.op_calls + self.ac_calls + self.transient_calls


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _empty_state(policy: str, parameters: Mapping[str, float | int]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy": policy,
        "parameters": dict(parameters),
        "completed_analyses": [],
        "metrics": {name: None for name in CANONICAL_METRICS},
        "statuses": {
            "ugf_status": "not_run",
            "phase_margin_status": "not_run",
            "ugf_crossing_count": 0,
            "positive_slew_status": "not_run",
            "negative_slew_status": "not_run",
        },
        "evidence": {
            "operating_region_valid": None,
            "operating_region_mask": 0,
            "operating_region_types": [],
            "device_status": {},
            "device_quantities": {},
        },
        "analysis_errors": {"op": None, "ac": None, "transient": None},
        "process_elapsed_seconds": {"op": 0.0, "ac": 0.0, "transient": 0.0},
        "outer_elapsed_seconds": {"op": 0.0, "ac": 0.0, "transient": 0.0},
        "process_elapsed_estimated": {"op": False, "ac": False, "transient": False},
    }


def _load_or_initialize(
    path: Path,
    *,
    policy: str,
    parameters: Mapping[str, float | int],
) -> dict[str, Any]:
    if not path.is_file():
        return _empty_state(policy, parameters)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid Task 8 stage checkpoint: {exc}") from exc
    if (
        state.get("schema_version") != 1
        or state.get("policy") != policy
        or state.get("parameters") != dict(parameters)
    ):
        raise RuntimeError("Task 8 stage checkpoint identity changed")
    return state


def _write_netlist(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def execute_real_stage(
    kind: str,
    *,
    config: Sky130TwoStageOtaCircuitConfig,
    parameters: Mapping[str, float | int],
    directory: Path,
    executable: str,
    timeout_seconds: float,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
) -> StageMeasurement:
    """Execute and parse exactly one frozen Task 7 analysis."""
    started = monotonic()
    process_elapsed = 0.0
    estimated = False
    metrics: dict[str, float | None] = {}
    statuses: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    error: str | None = None
    directory.mkdir(parents=True, exist_ok=True)
    process_started: float | None = None
    try:
        with sky130_runtime_paths(config.model, directory) as paths:
            windows_runtime = os.name == "nt"
            runtime_data = Path(paths.runtime_ac) if windows_runtime else paths.ac_path
            runtime_op = Path(paths.runtime_op) if windows_runtime else paths.op_path
            runtime_device = (
                Path(paths.runtime_device) if windows_runtime else paths.device_path
            )
            for output in (
                runtime_data,
                runtime_op,
                runtime_device,
                paths.runtime_log,
            ):
                output.unlink(missing_ok=True)
            common = {
                "invariant_path": paths.runtime_invariant,
                "nfet_corner_path": paths.runtime_corner,
                "pfet_corner_path": paths.runtime_pfet_corner,
            }
            if kind == "op":
                text = generate_task7_op_netlist(
                    config,
                    parameters,
                    **common,
                    op_output_path=paths.runtime_op,
                    device_op_output_path=paths.runtime_device,
                )
            elif kind == "ac":
                text = generate_task7_ac_netlist(
                    config,
                    parameters,
                    **common,
                    ac_output_path=paths.runtime_ac,
                    start_frequency_hz=start_frequency_hz,
                    stop_frequency_hz=stop_frequency_hz,
                    points_per_decade=points_per_decade,
                )
            elif kind == "transient":
                text = generate_task7_transient_netlist(
                    config,
                    parameters,
                    **common,
                    transient_output_path=paths.runtime_ac,
                )
            else:
                raise ValueError(f"unknown Task 8 analysis kind '{kind}'")
            _write_netlist(Path(paths.runtime_netlist), text)
            process_started = monotonic()
            process = run_ngspice(
                paths.runtime_netlist,
                executable=executable,
                timeout_seconds=timeout_seconds,
                log_path=paths.runtime_log,
                preserve_runtime_paths=True,
            )
            process_elapsed = process.elapsed_seconds
            if kind == "op":
                op = parse_task7_operating_point(runtime_op, runtime_device)
                region = assess_task7_operating_regions(op)
                metrics = {
                    "dc_power_w": op.dc_power_w,
                    "supply_current_a": op.supply_current_a,
                    "output_dc_voltage": op.output_voltage_v,
                    "stage1_dc_voltage": op.stage1_voltage_v,
                    "operating_region_valid": float(region.valid),
                }
                evidence = {
                    "operating_region_valid": region.valid,
                    "operating_region_mask": region.violation_mask,
                    "operating_region_types": list(region.violation_types),
                    "device_status": dict(region.device_status),
                    "device_quantities": {
                        role: dict(values)
                        for role, values in op.device_quantities.items()
                    },
                }
            elif kind == "ac":
                response = parse_ac_output(runtime_data)
                stability = measure_task7_stability(response)
                metrics = {
                    "dc_gain_db": stability.dc_gain_db,
                    "ugf_hz": stability.ugf_hz,
                    "ugf_lower_bound_hz": stability.ugf_lower_bound_hz,
                    "phase_margin_deg": stability.phase_margin_deg,
                    "minus_3db_bandwidth_hz": optional_minus_3db_bandwidth(response),
                }
                statuses = {
                    "ugf_status": stability.ugf_status.value,
                    "phase_margin_status": stability.phase_margin_status.value,
                    "ugf_crossing_count": stability.crossing_count,
                }
            else:
                response = parse_task7_transient(runtime_data)
                slew = measure_task7_slew(response, config)
                metrics = {
                    "positive_slew_v_per_s": slew.positive_slew_v_per_s,
                    "negative_slew_v_per_s": slew.negative_slew_v_per_s,
                }
                statuses = {
                    "positive_slew_status": slew.positive_status.value,
                    "negative_slew_status": slew.negative_status.value,
                }
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        if process_started is not None and process_elapsed == 0.0:
            process_elapsed = max(0.0, monotonic() - process_started)
            estimated = True
        if kind == "ac":
            statuses = {
                "ugf_status": UgfStatus.ANALYSIS_ERROR.value,
                "phase_margin_status": PhaseMarginStatus.ANALYSIS_ERROR.value,
                "ugf_crossing_count": 0,
            }
        elif kind == "transient":
            statuses = {
                "positive_slew_status": SlewStatus.ANALYSIS_ERROR.value,
                "negative_slew_status": SlewStatus.ANALYSIS_ERROR.value,
            }
    return StageMeasurement(
        kind=kind,
        metrics=metrics,
        statuses=statuses,
        evidence=evidence,
        error=error,
        process_elapsed_seconds=process_elapsed,
        outer_elapsed_seconds=monotonic() - started,
        process_elapsed_estimated=estimated,
    )


def _terminal_from_state(
    state: dict[str, Any],
    *,
    evaluation_stage: str,
    first_blocking_constraint: str | None,
    objective_value: float | None,
    constraint_violation: float | None,
    constraint_components: Mapping[str, float],
    is_feasible: bool,
) -> Task8Evaluation:
    process = state["process_elapsed_seconds"]
    outer = state["outer_elapsed_seconds"]
    completed = set(state["completed_analyses"])
    accumulated = sum(float(process[name]) for name in ("op", "ac", "transient"))
    outer_total = sum(float(outer[name]) for name in ("op", "ac", "transient"))
    return Task8Evaluation(
        policy=state["policy"],
        evaluation_stage=evaluation_stage,
        first_blocking_constraint=first_blocking_constraint,
        simulation_status=(
            "success" if objective_value is not None else "analysis_failed"
        ),
        metrics=dict(state["metrics"]),
        statuses=dict(state["statuses"]),
        evidence=dict(state["evidence"]),
        analysis_errors=dict(state["analysis_errors"]),
        objective_value=objective_value,
        constraint_violation=constraint_violation,
        constraint_components=dict(constraint_components),
        is_feasible=is_feasible,
        ngspice_process_calls=len(completed),
        op_calls=int("op" in completed),
        ac_calls=int("ac" in completed),
        transient_calls=int("transient" in completed),
        accumulated_ngspice_seconds=accumulated,
        outer_wall_seconds=outer_total,
        orchestration_seconds=max(0.0, outer_total - accumulated),
        process_elapsed_estimate_count=sum(
            bool(value) for value in state["process_elapsed_estimated"].values()
        ),
    )


def evaluate_task8_candidate(
    config: Sky130TwoStageOtaCircuitConfig,
    parameters: Mapping[str, float | int],
    evaluation_directory: Path,
    *,
    policy: str,
    executable: str,
    timeout_seconds: float,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
    stage_runner: Callable[[str, Path], StageMeasurement] | None = None,
    stop_after_stage: str | None = None,
) -> Task8Evaluation:
    """Evaluate one candidate, durably resuming after OP or AC if interrupted."""
    if policy not in {"full", "hierarchical"}:
        raise ValueError("Task 8 policy must be full or hierarchical")
    root = evaluation_directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    checkpoint = root / CHECKPOINT_FILENAME
    state = _load_or_initialize(checkpoint, policy=policy, parameters=parameters)

    def run_stage(kind: str) -> None:
        if kind in state["completed_analyses"]:
            return
        if stage_runner is None:
            measured = execute_real_stage(
                kind,
                config=config,
                parameters=parameters,
                directory=root / kind,
                executable=executable,
                timeout_seconds=timeout_seconds,
                start_frequency_hz=start_frequency_hz,
                stop_frequency_hz=stop_frequency_hz,
                points_per_decade=points_per_decade,
            )
        else:
            measured = stage_runner(kind, root / kind)
        if measured.kind != kind:
            raise ValueError("Task 8 stage runner returned the wrong analysis kind")
        state["metrics"].update(measured.metrics)
        state["statuses"].update(measured.statuses)
        state["evidence"].update(measured.evidence)
        state["analysis_errors"][kind] = measured.error
        state["process_elapsed_seconds"][kind] = measured.process_elapsed_seconds
        state["outer_elapsed_seconds"][kind] = measured.outer_elapsed_seconds
        state["process_elapsed_estimated"][kind] = (
            measured.process_elapsed_estimated
        )
        state["completed_analyses"].append(kind)
        _atomic_json(checkpoint, state)
        if stop_after_stage == kind:
            raise StageBoundaryReached(f"stopped after durable {kind} boundary")

    run_stage("op")
    if state["analysis_errors"]["op"] is not None and policy == "hierarchical":
        return _terminal_from_state(
            state,
            evaluation_stage="analysis_failed",
            first_blocking_constraint=None,
            objective_value=None,
            constraint_violation=None,
            constraint_components={},
            is_feasible=False,
        )
    op = (
        op_gate(state["metrics"])
        if state["analysis_errors"]["op"] is None
        else None
    )
    if policy == "hierarchical" and op is not None and not op.passed:
        objective = hierarchical_objective(
            "op_rejected",
            op.violation_sum,
            state["metrics"],
            ugf_status=state["statuses"]["ugf_status"],
            phase_margin_status=state["statuses"]["phase_margin_status"],
            positive_slew_status=state["statuses"]["positive_slew_status"],
            negative_slew_status=state["statuses"]["negative_slew_status"],
        )
        return _terminal_from_state(
            state,
            evaluation_stage="op_rejected",
            first_blocking_constraint=op.first_blocking_constraint,
            objective_value=objective,
            constraint_violation=op.violation_sum,
            constraint_components={"op_stage": op.violation_sum},
            is_feasible=False,
        )

    run_stage("ac")
    if state["analysis_errors"]["ac"] is not None and policy == "hierarchical":
        return _terminal_from_state(
            state,
            evaluation_stage="analysis_failed",
            first_blocking_constraint=None,
            objective_value=None,
            constraint_violation=None,
            constraint_components={},
            is_feasible=False,
        )
    ac = None
    if state["analysis_errors"]["ac"] is None:
        ac = ac_gate(
            state["metrics"],
            ugf_status=state["statuses"]["ugf_status"],
            phase_margin_status=state["statuses"]["phase_margin_status"],
        )
    if policy == "hierarchical" and ac is not None and not ac.passed:
        objective = hierarchical_objective(
            "ac_rejected",
            ac.violation_sum,
            state["metrics"],
            ugf_status=state["statuses"]["ugf_status"],
            phase_margin_status=state["statuses"]["phase_margin_status"],
            positive_slew_status=state["statuses"]["positive_slew_status"],
            negative_slew_status=state["statuses"]["negative_slew_status"],
        )
        return _terminal_from_state(
            state,
            evaluation_stage="ac_rejected",
            first_blocking_constraint=ac.first_blocking_constraint,
            objective_value=objective,
            constraint_violation=ac.violation_sum,
            constraint_components={"ac_stage": ac.violation_sum},
            is_feasible=False,
        )

    run_stage("transient")
    if any(state["analysis_errors"].values()):
        return _terminal_from_state(
            state,
            evaluation_stage="analysis_failed",
            first_blocking_constraint=None,
            objective_value=None,
            constraint_violation=None,
            constraint_components={},
            is_feasible=False,
        )
    objective = evaluate_task7_objective(
        state["metrics"],
        TASK8_SPECIFICATION,
        ugf_status=state["statuses"]["ugf_status"],
        phase_margin_status=state["statuses"]["phase_margin_status"],
        positive_slew_status=state["statuses"]["positive_slew_status"],
        negative_slew_status=state["statuses"]["negative_slew_status"],
    )
    transient = transient_gate(
        state["metrics"],
        positive_slew_status=state["statuses"]["positive_slew_status"],
        negative_slew_status=state["statuses"]["negative_slew_status"],
    )
    if policy == "full":
        stage = "fully_feasible" if objective.is_feasible else "full_infeasible"
        blocker = (
            None
            if objective.is_feasible
            else (
                (None if op is None else op.first_blocking_constraint)
                or (None if ac is None else ac.first_blocking_constraint)
                or transient.first_blocking_constraint
            )
        )
        value = objective.objective_value
    else:
        stage = transient.evaluation_stage
        blocker = transient.first_blocking_constraint
        value = (
            objective.objective_value
            if objective.is_feasible
            else hierarchical_objective(
                stage,
                transient.violation_sum,
                state["metrics"],
                ugf_status=state["statuses"]["ugf_status"],
                phase_margin_status=state["statuses"]["phase_margin_status"],
                positive_slew_status=state["statuses"]["positive_slew_status"],
                negative_slew_status=state["statuses"]["negative_slew_status"],
            )
        )
    return _terminal_from_state(
        state,
        evaluation_stage=stage,
        first_blocking_constraint=blocker,
        objective_value=value,
        constraint_violation=objective.constraint_violation,
        constraint_components=objective.constraint_components,
        is_feasible=objective.is_feasible,
    )
