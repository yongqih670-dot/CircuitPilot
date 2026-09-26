"""Truthful corrected-v2 exact/partial robust feedback for Task 9.6."""

from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
from typing import Any, Mapping

from circuitpilot.sky130_two_stage_ota import DEVICE_ROLES, PFET_ROLES
from circuitpilot.task9_protocol import CANONICAL_CORNER_ORDER, CONSTRAINT_NAMES, STAGE_COMPONENTS
from circuitpilot.task9_5_benchmark import benchmark_v2_hash
from circuitpilot.task9_5_region import V2_SEMANTICS, classify_device


STAGES = ("op", "ac", "transient")


def _parameter_hash(parameters: Mapping[str, float | int]) -> str:
    payload = json.dumps(dict(parameters), sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    return sha256(payload.encode()).hexdigest()


def _margin_penalty(corners: list[Mapping[str, Any]]) -> float | None:
    penalties = []
    for corner in corners:
        if "op" not in corner.get("completed_analyses", ()):
            continue
        if corner.get("analysis_errors", {}).get("op") is not None:
            continue
        devices = (corner.get("evidence") or {}).get("device_quantities", {})
        for role in DEVICE_ROLES:
            values = devices.get(role, {})
            if not {"vgs", "vds", "vth", "vdsat"} <= set(values):
                continue
            vgs, vds, vth, vdsat = (
                float(values[name]) for name in ("vgs", "vds", "vth", "vdsat")
            )
            if all(isfinite(value) for value in (vgs, vds, vth, vdsat)):
                penalties.append(max(0.0, vth - vgs) / 0.01
                                 + max(0.0, vdsat - vds) / 0.01)
    return sum(penalties) if penalties else None


def summarize_v2_robust_feedback(result: Mapping[str, Any]) -> dict[str, Any]:
    """Never promote missing measurements to exact zero/pass.

    A complete Full matrix with valid application checks is exact. Every
    Hierarchical/OP-only result remains diagnostic even if it happens to
    measure all stages, because final ranking requires independent Full-PVT.
    """
    if result.get("benchmark_v2_hash") != benchmark_v2_hash():
        raise ValueError("Task 9.6 requires the approved corrected Benchmark v2 hash")
    mode = result.get("mode")
    if mode not in {"full", "hierarchical", "op_only"}:
        raise ValueError("unknown Task 9.6 evaluation mode")
    corners = result.get("corners")
    if not isinstance(corners, list) or len(corners) != 15:
        raise ValueError("Task 9.6 requires 15 explicit corner records")
    by_id = {corner.get("corner_id"): corner for corner in corners}
    if len(by_id) != 15 or set(by_id) != set(CANONICAL_CORNER_ORDER):
        raise ValueError("Task 9.6 corner identity mismatch")

    unknown = []
    lower_by_constraint: dict[str, float | None] = {name: None for name in CONSTRAINT_NAMES}
    normalized_corners = []
    passed_stages = 0
    passed_corners = 0
    invalid_measured = False
    measured_stages = 0
    for corner_id in CANONICAL_CORNER_ORDER:
        corner = by_id[corner_id]
        completed = corner.get("completed_analyses", ())
        if len(set(completed)) != len(completed) or not set(completed) <= set(STAGES):
            raise ValueError(f"invalid completed stages at {corner_id}")
        components = corner.get("constraint_components") or {}
        errors = corner.get("analysis_errors") or {}
        application = corner.get("application_checks") or {}
        known: dict[str, float | None] = {name: None for name in CONSTRAINT_NAMES}
        corner_pass = len(completed) == 3
        corner_passed_stages = 0
        for stage in STAGES:
            if stage not in completed:
                unknown.append({"corner_id": corner_id, "stage": stage})
                corner_pass = False
                continue
            measured_stages += 1
            if errors.get(stage) is not None:
                invalid_measured = True
                corner_pass = False
                continue
            stage_components = STAGE_COMPONENTS[stage]
            for name in stage_components:
                value = components.get(name)
                if value is None or not isfinite(float(value)) or float(value) < 0:
                    invalid_measured = True
                    corner_pass = False
                    continue
                numeric = float(value)
                known[name] = numeric
                old = lower_by_constraint[name]
                lower_by_constraint[name] = numeric if old is None else max(old, numeric)
            stage_valid = all(known[name] is not None for name in stage_components)
            if stage_valid and all(known[name] == 0 for name in stage_components):
                corner_passed_stages += 1
            else:
                corner_pass = False
        if completed and (
            application.get("vdd_applied") is not True
            or application.get("temperature_applied_all_completed_stages") is not True
        ):
            invalid_measured = True
            corner_pass = False
        else:
            passed_stages += corner_passed_stages
        if corner_pass:
            passed_corners += 1
        if "op" in completed and errors.get("op") is None:
            evidence = corner.get("evidence") or {}
            if evidence.get("region_semantics") != V2_SEMANTICS:
                raise ValueError(f"non-v2 region semantics at {corner_id}")
            devices = evidence.get("device_quantities", {})
            region_pass = all(
                classify_device(devices.get(role, {}), version=V2_SEMANTICS,
                                pfet=role in PFET_ROLES) == "saturation"
                for role in DEVICE_ROLES
            )
            if float((corner.get("metrics") or {}).get("operating_region_valid", -1)) != float(region_pass):
                raise ValueError(f"v2 operating-region value mismatch at {corner_id}")
        normalized_corners.append({"corner_id": corner_id,
                                   "completed_analyses": list(completed),
                                   "constraint_components": known})

    complete = measured_stages == 45 and not unknown
    if result.get("process_calls") != measured_stages:
        raise ValueError("reported process count does not match completed analyses")
    full_exact = mode == "full" and complete and not invalid_measured
    if mode == "full" and result.get("process_calls") != 45:
        full_exact = False
    if full_exact and result.get("complete_full_matrix") is not True:
        full_exact = False
    exact = (sum(float(lower_by_constraint[name]) for name in CONSTRAINT_NAMES)
             if full_exact and all(value is not None for value in lower_by_constraint.values())
             else None)
    if exact is not None and bool(result.get("is_feasible")) != (exact == 0.0):
        raise ValueError("Full-PVT feasibility contradicts exact v2 violation")
    if mode == "full" and exact is None:
        status = "invalid_full"
    elif exact is not None:
        status = "exact"
    else:
        status = "partial"
    available = [value for value in lower_by_constraint.values() if value is not None]
    lower_bound = sum(available) if available else None
    penalty = _margin_penalty(corners)
    eligible = mode != "full" and measured_stages > 0 and not invalid_measured
    parameter_hash = _parameter_hash(result.get("parameters", {}))
    order_key = (
        [-passed_stages, -passed_corners, lower_bound, penalty, parameter_hash]
        if eligible and lower_bound is not None and penalty is not None else None
    )
    return {
        "schema_version": "task9_6_robust_feedback_v1",
        "benchmark_v2_hash": benchmark_v2_hash(),
        "region_semantics": V2_SEMANTICS,
        "evaluation_mode": mode,
        "robust_evaluation_status": status,
        "exact_robust_violation": exact,
        "measured_robust_violation_lower_bound": lower_bound,
        "measured_constraint_lower_bounds": lower_by_constraint,
        "unknown_analyses": unknown,
        "measured_analysis_count": measured_stages,
        "passed_measured_stages": passed_stages,
        "passed_complete_corners": passed_corners,
        "partial_search_score": {
            "eligible": eligible and order_key is not None,
            "ordering_key": order_key,
            "device_margin_penalty": penalty,
            "parameter_hash": parameter_hash,
        } if mode != "full" else None,
        "final_ranking_eligible": full_exact,
        "corner_feedback": normalized_corners,
    }
