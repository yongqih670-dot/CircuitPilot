"""Independent diagnostic PVT evaluator with corrected v2 region semantics."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from circuitpilot.experiments.task9_evaluator import execute_real_pvt_stage
from circuitpilot.sky130_two_stage_ota import DEVICE_ROLES, PFET_ROLES, Sky130TwoStageOtaCircuitConfig
from circuitpilot.task9_protocol import (
    CANONICAL_CORNER_ORDER, CORNER_BY_ID, DEFAULT_STATUSES, STAGE_COMPONENTS,
    STATIC_WORST_FIRST_ORDER, corner_constraint_components,
)
from circuitpilot.task9_5_benchmark import benchmark_v2_hash
from circuitpilot.task9_5_region import V2_SEMANTICS, classify_device


def region_v2_evidence(devices: Mapping[str, Mapping[str, float]]) -> tuple[bool, dict[str, str]]:
    statuses = {
        role: classify_device(devices.get(role, {}), version=V2_SEMANTICS,
                              pfet=role in PFET_ROLES)
        for role in DEVICE_ROLES
    }
    return all(value == "saturation" for value in statuses.values()), statuses


def op_margin_score(devices: Mapping[str, Mapping[str, float]]) -> float:
    """Smooth diagnostic distance from a modest on/headroom margin."""
    score = 0.0
    for role in DEVICE_ROLES:
        values = devices.get(role, {})
        if not {"vgs", "vds", "vth", "vdsat"} <= set(values):
            score += 10.0
            continue
        on = float(values["vgs"]) - float(values["vth"])
        headroom = float(values["vds"]) - float(values["vdsat"])
        score += max(0.0, 0.01 - on) / 0.05 + max(0.0, 0.01 - headroom) / 0.05
    return score


def evaluate_v2_candidate(
    *,
    base_config: Sky130TwoStageOtaCircuitConfig,
    parameters: Mapping[str, float | int],
    evaluation_directory: Path,
    executable: str,
    timeout_seconds: float,
    start_frequency_hz: float,
    stop_frequency_hz: float,
    points_per_decade: int,
    mode: str,
    corners: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Evaluate OP-only, safe hierarchy, or complete Full-PVT from scratch.

    OP-only is a diagnostic search objective, never a feasibility verdict.
    Full mode always performs all 45 analyses.  Hierarchical mode stops only
    after an actual stage measurement proves a frozen hard-constraint failure.
    """
    if mode not in {"op_only", "hierarchical", "full"}:
        raise ValueError("invalid Task 9.5 diagnostic evaluation mode")
    order = tuple(corners or (CANONICAL_CORNER_ORDER if mode == "full"
                              else STATIC_WORST_FIRST_ORDER))
    if len(set(order)) != len(order) or not set(order) <= set(CANONICAL_CORNER_ORDER):
        raise ValueError("invalid corner subset/order")
    if mode != "op_only" and set(order) != set(CANONICAL_CORNER_ORDER):
        raise ValueError("Full/hierarchical verification requires all 15 corners")
    root = evaluation_directory.resolve()
    root.mkdir(parents=True, exist_ok=True)
    outcomes: dict[str, dict[str, Any]] = {}
    first_failure = None
    process_calls = 0
    process_seconds = 0.0
    for corner_id in order:
        descriptor = CORNER_BY_ID[corner_id]
        item: dict[str, Any] = {
            **descriptor.to_dict(), "completed_analyses": [],
            "metrics": {}, "statuses": dict(DEFAULT_STATUSES),
            "evidence": {}, "analysis_errors": {}, "process_elapsed_seconds": {},
            "reported_temperature_c": {}, "application_checks": {},
            "constraint_components": {},
        }
        outcomes[corner_id] = item
        for stage in (("op",) if mode == "op_only" else ("op", "ac", "transient")):
            measured = execute_real_pvt_stage(
                stage, base_config=base_config, corner_id=corner_id,
                parameters=parameters, directory=root / corner_id / stage,
                executable=executable, timeout_seconds=timeout_seconds,
                start_frequency_hz=start_frequency_hz,
                stop_frequency_hz=stop_frequency_hz,
                points_per_decade=points_per_decade,
            )
            process_calls += 1
            process_seconds += measured.process_elapsed_seconds
            item["completed_analyses"].append(stage)
            item["metrics"].update(measured.metrics)
            item["statuses"].update(measured.statuses)
            item["evidence"].update(measured.evidence)
            item["analysis_errors"][stage] = measured.error
            item["process_elapsed_seconds"][stage] = measured.process_elapsed_seconds
            item["reported_temperature_c"][stage] = measured.reported_temperature_c
            if stage == "op" and measured.error is None:
                valid, statuses = region_v2_evidence(
                    item["evidence"].get("device_quantities", {}))
                item["metrics"]["operating_region_valid"] = float(valid)
                item["evidence"]["device_status_v2"] = statuses
                item["evidence"]["region_semantics"] = V2_SEMANTICS
            components = corner_constraint_components(item["metrics"], item["statuses"])
            vdd = item["evidence"].get("measured_supply_voltage_v")
            item["application_checks"] = {
                "vdd_applied": vdd is not None
                and abs(float(vdd) - float(item["vdd_v"])) <= 1e-9,
                "temperature_applied_all_completed_stages": all(
                    value is not None
                    and abs(float(value) - float(item["temperature_c"])) <= 1e-9
                    for value in item["reported_temperature_c"].values()
                ),
            }
            item["constraint_components"] = {
                name: float(components[name])
                for completed_stage in item["completed_analyses"]
                for name in STAGE_COMPONENTS[completed_stage]
            }
            blocker = ("analysis_error" if measured.error else next(
                (name for name in STAGE_COMPONENTS[stage] if components[name] > 0), None))
            if blocker is None and not all(item["application_checks"].values()):
                blocker = "corner_application"
            if blocker is not None and first_failure is None:
                first_failure = {"corner_id": corner_id, "stage": stage,
                                 "constraint": blocker}
            if blocker is not None and mode == "hierarchical":
                break
        if first_failure is not None and mode == "hierarchical":
            break
    completed = mode != "op_only" and len(outcomes) == 15 and all(
        set(item["completed_analyses"]) == {"op", "ac", "transient"}
        for item in outcomes.values())
    feasible = completed and all(
        all(value <= 0 for value in item["constraint_components"].values())
        and not any(item["analysis_errors"].values())
        and all(item["application_checks"].values())
        for item in outcomes.values())
    op_score = sum(
        op_margin_score(item["evidence"].get("device_quantities", {}))
        + 10.0 * sum(item["constraint_components"].get(name, 0)
                     for name in STAGE_COMPONENTS["op"])
        for item in outcomes.values()
    )
    all_corners = []
    for corner_id in CANONICAL_CORNER_ORDER:
        all_corners.append(outcomes.get(corner_id, {
            **CORNER_BY_ID[corner_id].to_dict(), "completed_analyses": [],
            "metrics": None, "statuses": None, "evidence": None,
            "analysis_errors": None, "process_elapsed_seconds": None,
            "reported_temperature_c": None, "application_checks": None,
            "constraint_components": None,
        }))
    return {
        "benchmark_v2_hash": benchmark_v2_hash(), "mode": mode,
        "parameters": dict(parameters), "is_feasible": feasible,
        "complete_full_matrix": completed and mode == "full",
        "first_failure": first_failure, "process_calls": process_calls,
        "accumulated_ngspice_seconds": process_seconds,
        "op_margin_score": op_score,
        "op_valid_corner_count": sum(
            item["metrics"].get("operating_region_valid") == 1.0
            for item in outcomes.values()),
        "corners": all_corners,
    }
