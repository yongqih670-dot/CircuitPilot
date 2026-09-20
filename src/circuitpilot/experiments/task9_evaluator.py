"""Resumable Full-PVT and safe hierarchical evaluators for Task 9."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from time import monotonic, sleep
from typing import Any, Mapping

from circuitpilot.parser import parse_ac_output
from circuitpilot.simulator import run_ngspice
from circuitpilot.sky130_pvt import task9_corner_config, task9_runtime_paths
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
from circuitpilot.task9_protocol import (
    CANONICAL_CORNER_ORDER,
    CANONICAL_METRICS,
    CONSTRAINT_NAMES,
    CORNER_BY_ID,
    CORNER_ORDER_HASH,
    DEFAULT_STATUSES,
    PVT_BENCHMARK_HASH,
    STATIC_WORST_FIRST_ORDER,
    TASK9_PROTOCOL_HASH,
    corner_constraint_components,
    partial_feedback,
    policy_hash,
    robust_objective,
    stage_decision,
    worst_corner_summary,
)


CHECKPOINT_FILENAME = "pvt_checkpoint.json"
TEMPERATURE_PATTERN = re.compile(r"Doing analysis at TEMP\s*=\s*([-+0-9.eE]+)")


class StageBoundaryReached(RuntimeError):
    """Test-only interruption after a durable Task 9 stage checkpoint."""


@dataclass(frozen=True, slots=True)
class PVTFullEvaluationPolicy:
    name: str = "full"
    corner_order: tuple[str, ...] = CANONICAL_CORNER_ORDER
    short_circuit: bool = False


@dataclass(frozen=True, slots=True)
class PVTHierarchicalEvaluationPolicy:
    name: str = "hierarchical"
    corner_order: tuple[str, ...] = STATIC_WORST_FIRST_ORDER
    short_circuit: bool = True


@dataclass(frozen=True, slots=True)
class StageMeasurement:
    kind: str
    metrics: dict[str, float | None]
    statuses: dict[str, Any]
    evidence: dict[str, Any]
    error: str | None
    process_elapsed_seconds: float
    outer_elapsed_seconds: float
    process_elapsed_estimated: bool
    reported_temperature_c: float | None


@dataclass(frozen=True, slots=True)
class Task9Evaluation:
    policy: str
    evaluation_stage: str
    first_failing_corner: str | None
    first_failing_stage: str | None
    first_failing_constraint: str | None
    simulation_status: str
    corner_results: tuple[dict[str, Any], ...]
    worst_metrics: dict[str, Any]
    objective_value: float
    robust_constraint_violation: float
    constraint_components: dict[str, float]
    is_feasible: bool
    progress_units: int
    feedback_tier: tuple[int, int, float]
    corners_started: int
    corners_completed: int
    op_calls: int
    ac_calls: int
    transient_calls: int
    process_calls: int
    accumulated_ngspice_seconds: float
    outer_wall_seconds: float
    orchestration_seconds: float
    process_elapsed_estimate_count: int


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    last_error: PermissionError | None = None
    for delay in (0.0, 0.01, 0.05, 0.1, 0.25, 0.5):
        if delay:
            sleep(delay)
        try:
            temporary.replace(path)
            return
        except PermissionError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _empty_corner(corner_id: str) -> dict[str, Any]:
    corner = CORNER_BY_ID[corner_id]
    return {
        **corner.to_dict(),
        "started": False,
        "completed_analyses": [],
        "metrics": {name: None for name in CANONICAL_METRICS},
        "statuses": dict(DEFAULT_STATUSES),
        "evidence": {},
        "analysis_errors": {"op": None, "ac": None, "transient": None},
        "process_elapsed_seconds": {"op": 0.0, "ac": 0.0, "transient": 0.0},
        "outer_elapsed_seconds": {"op": 0.0, "ac": 0.0, "transient": 0.0},
        "process_elapsed_estimated": {"op": False, "ac": False, "transient": False},
        "reported_temperature_c": {"op": None, "ac": None, "transient": None},
        "constraint_components": {name: None for name in CONSTRAINT_NAMES},
        "constraint_violation": None,
        "corner_feasible": None,
        "application_checks": {
            "vdd_applied": None,
            "temperature_applied_all_completed_stages": None,
        },
    }


def _empty_state(policy: str, parameters: Mapping[str, float | int]) -> dict[str, Any]:
    return {
        "schema_version": "task9_pvt_checkpoint_v1",
        "policy": policy,
        "parameters": dict(parameters),
        "task9_protocol_hash": TASK9_PROTOCOL_HASH,
        "pvt_benchmark_hash": PVT_BENCHMARK_HASH,
        "policy_hash": policy_hash(policy),
        "corner_order_hash": CORNER_ORDER_HASH,
        "corner_results": {corner_id: _empty_corner(corner_id) for corner_id in CANONICAL_CORNER_ORDER},
        "terminal": None,
    }


def _load_or_initialize(
    path: Path, *, policy: str, parameters: Mapping[str, float | int]
) -> dict[str, Any]:
    if not path.is_file():
        return _empty_state(policy, parameters)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid Task 9 checkpoint: {exc}") from exc
    expected = _empty_state(policy, parameters)
    for name in (
        "schema_version",
        "policy",
        "parameters",
        "task9_protocol_hash",
        "pvt_benchmark_hash",
        "policy_hash",
        "corner_order_hash",
    ):
        if state.get(name) != expected[name]:
            raise RuntimeError(f"Task 9 checkpoint identity changed at {name}")
    return state


def execute_real_pvt_stage(
    kind: str,
    *,
    base_config: Sky130TwoStageOtaCircuitConfig,
    corner_id: str,
    parameters: Mapping[str, float | int],
    directory: Path,
    executable: str,
    timeout_seconds: float,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
) -> StageMeasurement:
    if kind not in {"op", "ac", "transient"}:
        raise ValueError(f"unknown Task 9 analysis kind '{kind}'")
    corner = CORNER_BY_ID[corner_id]
    config = task9_corner_config(base_config, corner)
    started = monotonic()
    process_elapsed = 0.0
    estimated = False
    process_started: float | None = None
    metrics: dict[str, float | None] = {}
    statuses: dict[str, Any] = {}
    evidence: dict[str, Any] = {}
    error: str | None = None
    reported_temperature: float | None = None
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with task9_runtime_paths(base_config.model, corner.process_corner, directory) as paths:
            runtime_data = Path(paths.runtime_ac)
            runtime_op = Path(paths.runtime_op)
            runtime_device = Path(paths.runtime_device)
            for output in (runtime_data, runtime_op, runtime_device, paths.runtime_log):
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
            else:
                text = generate_task7_transient_netlist(
                    config,
                    parameters,
                    **common,
                    transient_output_path=paths.runtime_ac,
                )
            Path(paths.runtime_netlist).write_text(text, encoding="utf-8")
            process_started = monotonic()
            process = run_ngspice(
                paths.runtime_netlist,
                executable=executable,
                timeout_seconds=timeout_seconds,
                log_path=paths.runtime_log,
                preserve_runtime_paths=True,
            )
            process_elapsed = process.elapsed_seconds
            log_text = Path(paths.runtime_log).read_text(encoding="utf-8", errors="replace")
            match = TEMPERATURE_PATTERN.search(log_text)
            if match is not None:
                reported_temperature = float(match.group(1))
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
                    "measured_supply_voltage_v": op.supply_voltage_v,
                    "operating_region_mask": region.violation_mask,
                    "operating_region_types": list(region.violation_types),
                    "device_status": dict(region.device_status),
                    "device_quantities": {
                        role: dict(values) for role, values in op.device_quantities.items()
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
        kind,
        metrics,
        statuses,
        evidence,
        error,
        process_elapsed,
        monotonic() - started,
        estimated,
        reported_temperature,
    )


def _apply_stage(corner: dict[str, Any], measurement: StageMeasurement) -> None:
    kind = measurement.kind
    corner["started"] = True
    if kind not in corner["completed_analyses"]:
        corner["completed_analyses"].append(kind)
    corner["metrics"].update(measurement.metrics)
    corner["statuses"].update(measurement.statuses)
    corner["evidence"].update(measurement.evidence)
    corner["analysis_errors"][kind] = measurement.error
    corner["process_elapsed_seconds"][kind] = measurement.process_elapsed_seconds
    corner["outer_elapsed_seconds"][kind] = measurement.outer_elapsed_seconds
    corner["process_elapsed_estimated"][kind] = measurement.process_elapsed_estimated
    corner["reported_temperature_c"][kind] = measurement.reported_temperature_c


def _refresh_corner(corner: dict[str, Any]) -> None:
    completed = set(corner["completed_analyses"])
    component_stage = {
        "gain_min": "ac",
        "ugf_min": "ac",
        "phase_margin_min": "ac",
        "power_max": "op",
        "positive_slew_min": "transient",
        "negative_slew_min": "transient",
        "output_low": "op",
        "output_high": "op",
        "operating_region": "op",
    }
    measured = corner_constraint_components(corner["metrics"], corner["statuses"])
    corner["constraint_components"] = {
        name: measured[name] if stage in completed else None
        for name, stage in component_stage.items()
    }
    if completed == {"op", "ac", "transient"}:
        values = {name: float(measured[name]) for name in CONSTRAINT_NAMES}
        corner["constraint_components"] = values
        corner["constraint_violation"] = sum(values.values())
        corner["corner_feasible"] = corner["constraint_violation"] == 0.0
    else:
        corner["constraint_violation"] = None
        corner["corner_feasible"] = None
    vdd = corner["evidence"].get("measured_supply_voltage_v")
    corner["application_checks"]["vdd_applied"] = (
        None if "op" not in completed or vdd is None else abs(float(vdd) - float(corner["vdd_v"])) <= 1e-9
    )
    temperatures = [
        corner["reported_temperature_c"][kind] for kind in corner["completed_analyses"]
    ]
    corner["application_checks"]["temperature_applied_all_completed_stages"] = (
        None
        if not temperatures
        else all(
            value is not None and abs(float(value) - float(corner["temperature_c"])) <= 1e-9
            for value in temperatures
        )
    )


def _progress(corners: Mapping[str, dict[str, Any]], order: tuple[str, ...]) -> int:
    progress = 0
    for corner_id in order:
        corner = corners[corner_id]
        completed = set(corner["completed_analyses"])
        for stage in ("op", "ac", "transient"):
            if stage not in completed:
                return progress
            if corner["analysis_errors"][stage] is not None:
                return progress
            decision = stage_decision(stage, corner["metrics"], corner["statuses"])
            if not decision.passed:
                return progress
            progress += 1
    return progress


def _first_failure(
    corners: Mapping[str, dict[str, Any]], order: tuple[str, ...]
) -> tuple[str | None, str | None, str | None, str | None]:
    for corner_id in order:
        corner = corners[corner_id]
        for stage in ("op", "ac", "transient"):
            if stage not in corner["completed_analyses"]:
                return None, None, None, None
            if corner["analysis_errors"][stage] is not None:
                return corner_id, stage, "invalid_required_measurement", "analysis_failed"
            decision = stage_decision(stage, corner["metrics"], corner["statuses"])
            if not decision.passed:
                return corner_id, stage, decision.first_blocking_constraint, f"{stage}_rejected"
    return None, None, None, None


def _terminal_evaluation(
    state: dict[str, Any], *, policy: str, started_at: float
) -> Task9Evaluation:
    order = CANONICAL_CORNER_ORDER if policy == "full" else STATIC_WORST_FIRST_ORDER
    corners_map = state["corner_results"]
    corners = tuple(corners_map[corner_id] for corner_id in CANONICAL_CORNER_ORDER)
    completed_all = all(
        set(corner["completed_analyses"]) == {"op", "ac", "transient"}
        for corner in corners
    )
    errors = [
        value
        for corner in corners
        for value in corner["analysis_errors"].values()
        if value is not None
    ]
    first_corner, first_stage, first_constraint, rejection_stage = _first_failure(
        corners_map, order
    )
    progress = _progress(corners_map, order)
    terminal = state.get("terminal") or {}
    budget_exhausted = bool(terminal.get("budget_exhausted"))
    if policy == "full" and not budget_exhausted:
        if not completed_all:
            raise RuntimeError("Full-PVT terminal result is incomplete")
        objective = robust_objective(corners)
        is_feasible = objective.pvt_feasible
        objective_value = objective.objective_value
        violation = objective.robust_constraint_violation
        components = dict(objective.robust_constraint_components)
        feedback_tier = (0, 0, objective_value) if is_feasible else (1, 0, violation)
        evaluation_stage = "pvt_feasible" if is_feasible else "full_infeasible"
    else:
        is_feasible = progress == 45 and not errors
        feedback = partial_feedback(corners, progress_units=progress, pvt_feasible=is_feasible)
        objective_value = feedback.objective_value
        violation = feedback.partial_robust_violation
        components = dict(feedback.partial_constraint_components)
        feedback_tier = feedback.lexicographic_tier
        evaluation_stage = "pvt_feasible" if is_feasible else (rejection_stage or "analysis_failed")
    if budget_exhausted:
        simulation_status = "budget_exhausted"
        evaluation_stage = "budget_exhausted"
        is_feasible = False
    elif errors:
        simulation_status = "analysis_failed"
        if policy == "hierarchical":
            evaluation_stage = "analysis_failed"
    else:
        simulation_status = "success"
    calls = {
        kind: sum(kind in corner["completed_analyses"] for corner in corners)
        for kind in ("op", "ac", "transient")
    }
    process_calls = sum(calls.values())
    process_seconds = sum(
        float(corner["process_elapsed_seconds"][kind])
        for corner in corners
        for kind in corner["completed_analyses"]
    )
    outer_seconds = sum(
        float(corner["outer_elapsed_seconds"][kind])
        for corner in corners
        for kind in corner["completed_analyses"]
    )
    return Task9Evaluation(
        policy=policy,
        evaluation_stage=evaluation_stage,
        first_failing_corner=first_corner,
        first_failing_stage=first_stage,
        first_failing_constraint=first_constraint,
        simulation_status=simulation_status,
        corner_results=corners,
        worst_metrics=worst_corner_summary(corners),
        objective_value=objective_value,
        robust_constraint_violation=violation,
        constraint_components=components,
        is_feasible=is_feasible,
        progress_units=progress,
        feedback_tier=feedback_tier,
        corners_started=sum(bool(corner["started"]) for corner in corners),
        corners_completed=sum(
            set(corner["completed_analyses"]) == {"op", "ac", "transient"}
            for corner in corners
        ),
        op_calls=calls["op"],
        ac_calls=calls["ac"],
        transient_calls=calls["transient"],
        process_calls=process_calls,
        accumulated_ngspice_seconds=process_seconds,
        outer_wall_seconds=outer_seconds,
        orchestration_seconds=max(0.0, monotonic() - started_at - outer_seconds),
        process_elapsed_estimate_count=sum(
            bool(corner["process_elapsed_estimated"][kind])
            for corner in corners
            for kind in corner["completed_analyses"]
        ),
    )


def evaluate_task9_candidate(
    *,
    policy: str,
    base_config: Sky130TwoStageOtaCircuitConfig,
    parameters: Mapping[str, float | int],
    evaluation_directory: Path,
    executable: str,
    timeout_seconds: float,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
    interrupt_after_stage: int | None = None,
    stop_after_accumulated_ngspice_seconds: float | None = None,
) -> Task9Evaluation:
    if policy not in {"full", "hierarchical"}:
        raise ValueError("Task 9 policy must be full or hierarchical")
    started_at = monotonic()
    root = evaluation_directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    checkpoint = root / CHECKPOINT_FILENAME
    state = _load_or_initialize(checkpoint, policy=policy, parameters=parameters)
    order = CANONICAL_CORNER_ORDER if policy == "full" else STATIC_WORST_FIRST_ORDER
    completed_count = sum(
        len(corner["completed_analyses"])
        for corner in state["corner_results"].values()
    )
    if stop_after_accumulated_ngspice_seconds is not None and stop_after_accumulated_ngspice_seconds <= 0.0:
        raise ValueError("Task 9 analysis-level budget must be positive")
    if state.get("terminal") is not None:
        return _terminal_evaluation(state, policy=policy, started_at=started_at)
    for corner_id in order:
        corner = state["corner_results"][corner_id]
        for kind in ("op", "ac", "transient"):
            if kind in corner["completed_analyses"]:
                if policy == "hierarchical":
                    if corner["analysis_errors"][kind] is not None:
                        state["terminal"] = {
                            "corner": corner_id,
                            "stage": kind,
                            "constraint": "invalid_required_measurement",
                        }
                        _atomic_json(checkpoint, state)
                        return _terminal_evaluation(state, policy=policy, started_at=started_at)
                    decision = stage_decision(kind, corner["metrics"], corner["statuses"])
                    if not decision.passed:
                        state["terminal"] = {
                            "corner": corner_id,
                            "stage": kind,
                            "constraint": decision.first_blocking_constraint,
                        }
                        _atomic_json(checkpoint, state)
                        return _terminal_evaluation(state, policy=policy, started_at=started_at)
                continue
            measurement = execute_real_pvt_stage(
                kind,
                base_config=base_config,
                corner_id=corner_id,
                parameters=parameters,
                directory=root / corner_id / kind,
                executable=executable,
                timeout_seconds=timeout_seconds,
                start_frequency_hz=start_frequency_hz,
                stop_frequency_hz=stop_frequency_hz,
                points_per_decade=points_per_decade,
            )
            _apply_stage(corner, measurement)
            _refresh_corner(corner)
            completed_count += 1
            _atomic_json(checkpoint, state)
            if interrupt_after_stage is not None and completed_count >= interrupt_after_stage:
                raise StageBoundaryReached(
                    f"interrupted after {completed_count} completed Task 9 stages"
                )
            if policy == "hierarchical":
                if measurement.error is not None:
                    state["terminal"] = {
                        "corner": corner_id,
                        "stage": kind,
                        "constraint": "invalid_required_measurement",
                    }
                    _atomic_json(checkpoint, state)
                    return _terminal_evaluation(state, policy=policy, started_at=started_at)
                decision = stage_decision(kind, corner["metrics"], corner["statuses"])
                if not decision.passed:
                    state["terminal"] = {
                        "corner": corner_id,
                        "stage": kind,
                        "constraint": decision.first_blocking_constraint,
                    }
                    _atomic_json(checkpoint, state)
                    return _terminal_evaluation(state, policy=policy, started_at=started_at)
            if stop_after_accumulated_ngspice_seconds is not None:
                candidate_seconds = sum(
                    float(item["process_elapsed_seconds"][stage])
                    for item in state["corner_results"].values()
                    for stage in item["completed_analyses"]
                )
                if candidate_seconds >= stop_after_accumulated_ngspice_seconds:
                    state["terminal"] = {"budget_exhausted": True}
                    _atomic_json(checkpoint, state)
                    return _terminal_evaluation(state, policy=policy, started_at=started_at)
    state["terminal"] = {"complete": True}
    _atomic_json(checkpoint, state)
    return _terminal_evaluation(state, policy=policy, started_at=started_at)
