"""Frozen pure semantics for Research Task 9 PVT optimization."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence

from circuitpilot.sky130_two_stage_ota import PhaseMarginStatus, SlewStatus, UgfStatus
from circuitpilot.task7_protocol import Task7Specification, stable_hash


TASK9_PROTOCOL_HASH = "feae5ad0f0b234814d36b567be9b5952934617a3ff3745983a0249fe38c7963b"
PVT_BENCHMARK_HASH = "ec2d4de0e0c5694598cc7444b4fa9b63a8d8b533fa68bdd504e5262ebd5e2d61"
CORNER_SUITE_HASH = "a97a333a89b5d709714e21e0a5497656fdbcc9168065f1113820a7513e013096"
CORNER_ORDER_HASH = "e07c17b9041c271e15d49d3362253db3a21fcd6eede169158dd18c7bb975fc56"
PVT_EVALUATION_POLICY_HASH = "6d63ca8809ec9afdfaad2e681c70ea4a189cfd5b48ff749757dfe883ef8b55a4"
FULL_POLICY_HASH = "7e3f976e361d459ec4fcff719a60a5ebd5dabed0f9d5b341cd67002791259b54"
HIERARCHICAL_POLICY_HASH = "6fc4c35c2bf17534cfeca62456cacc9c065524c55c9411a91e26e8f74b002629"
PARTIAL_FEEDBACK_HASH = "dd0063c0cc3c8e44c73a5607f3e8361162521f26c5d6ff40032ea81471f61fda"
COST_ACCOUNTING_HASH = "5978efd20ec05d4f1d827286fee0e0453e43fe141b8d8c24e1540f2e1ecafbf3"
SIMULATION_TIME_BUDGET_HASH = "9f2d7634c58cd161ac43d57485e3b5a89712153d1f9144035cb260c6dd863adf"

FORMAL_CANDIDATE_BUDGET = 20
FORMAL_SIMULATION_TIME_BUDGET_SECONDS = 375.41500000166707
FORMAL_SIMULATION_TIME_CANDIDATE_CAP = 100
SMOKE_CANDIDATE_BUDGET = 10
MAX_PROGRESS_UNITS = 45


@dataclass(frozen=True, slots=True)
class PVTCorner:
    corner_id: str
    process_corner: str
    condition: str
    vdd_v: float
    temperature_c: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "corner_id": self.corner_id,
            "process_corner": self.process_corner,
            "condition": self.condition,
            "vdd_v": self.vdd_v,
            "temperature_c": self.temperature_c,
        }


PVT_CORNERS = tuple(
    PVTCorner(f"{process}__{condition}", process, condition, vdd, temperature)
    for process in ("tt", "ss", "ff", "fs", "sf")
    for condition, vdd, temperature in (
        ("nominal", 1.80, 27.0),
        ("low_v_high_t", 1.62, 125.0),
        ("high_v_low_t", 1.98, -40.0),
    )
)
CORNER_BY_ID = {corner.corner_id: corner for corner in PVT_CORNERS}
CANONICAL_CORNER_ORDER = tuple(corner.corner_id for corner in PVT_CORNERS)
NOMINAL_FIRST_ORDER = (
    "tt__nominal",
    "ss__nominal",
    "ff__nominal",
    "fs__nominal",
    "sf__nominal",
    "tt__low_v_high_t",
    "ss__low_v_high_t",
    "ff__low_v_high_t",
    "fs__low_v_high_t",
    "sf__low_v_high_t",
    "tt__high_v_low_t",
    "ss__high_v_low_t",
    "ff__high_v_low_t",
    "fs__high_v_low_t",
    "sf__high_v_low_t",
)
STATIC_WORST_FIRST_ORDER = (
    "sf__nominal",
    "ss__low_v_high_t",
    "tt__low_v_high_t",
    "ff__low_v_high_t",
    "ss__nominal",
    "tt__nominal",
    "ff__nominal",
    "ss__high_v_low_t",
    "fs__low_v_high_t",
    "tt__high_v_low_t",
    "fs__nominal",
    "fs__high_v_low_t",
    "sf__low_v_high_t",
    "sf__high_v_low_t",
    "ff__high_v_low_t",
)

TASK9_SPECIFICATION = Task7Specification(
    gain_min_db=12.0,
    ugf_min_hz=5.0e5,
    phase_margin_min_deg=35.0,
    power_max_w=1.5e-3,
    positive_slew_min_v_per_s=5.0e5,
    negative_slew_min_v_per_s=5.0e5,
    output_min_v=0.10,
    output_max_v=1.70,
)
CONSTRAINT_NAMES = (
    "gain_min",
    "ugf_min",
    "phase_margin_min",
    "power_max",
    "positive_slew_min",
    "negative_slew_min",
    "output_low",
    "output_high",
    "operating_region",
)
CANONICAL_METRICS = (
    "dc_gain_db",
    "ugf_hz",
    "ugf_lower_bound_hz",
    "phase_margin_deg",
    "minus_3db_bandwidth_hz",
    "dc_power_w",
    "supply_current_a",
    "output_dc_voltage",
    "stage1_dc_voltage",
    "positive_slew_v_per_s",
    "negative_slew_v_per_s",
    "operating_region_valid",
)
DEFAULT_STATUSES = {
    "ugf_status": "not_run",
    "phase_margin_status": "not_run",
    "ugf_crossing_count": 0,
    "positive_slew_status": "not_run",
    "negative_slew_status": "not_run",
}


@dataclass(frozen=True, slots=True)
class StageDecision:
    passed: bool
    stage: str
    first_blocking_constraint: str | None


@dataclass(frozen=True, slots=True)
class RobustObjective:
    objective_value: float
    robust_constraint_violation: float
    robust_constraint_components: Mapping[str, float]
    pvt_feasible: bool
    worst_corner_power_w: float | None


@dataclass(frozen=True, slots=True)
class PartialFeedback:
    objective_value: float
    progress_units: int
    partial_robust_violation: float
    partial_constraint_components: Mapping[str, float]
    pvt_feasible: bool
    lexicographic_tier: tuple[int, int, float]


@dataclass(frozen=True, slots=True)
class ReplayAudit:
    replay_pvt_feasible: bool
    full_pvt_feasible: bool
    false_acceptance: bool
    false_rejection: bool
    corners_started: int
    op_calls: int
    ac_calls: int
    transient_calls: int
    first_failing_corner: str | None
    first_failing_stage: str | None
    first_failing_constraint: str | None


def policy_hash(policy: str) -> str:
    if policy == "full":
        return FULL_POLICY_HASH
    if policy == "hierarchical":
        return HIERARCHICAL_POLICY_HASH
    raise ValueError("Task 9 policy must be full or hierarchical")


def _finite(metrics: Mapping[str, float | None], name: str) -> float | None:
    value = metrics.get(name)
    if value is None:
        return None
    numeric = float(value)
    return numeric if isfinite(numeric) else None


def _lower(value: float | None, threshold: float, status_ok: bool = True) -> float:
    if value is None or not status_ok:
        return 1.0
    return max(0.0, threshold - value) / max(abs(threshold), 1e-30)


def _upper(value: float | None, threshold: float) -> float:
    if value is None:
        return 1.0
    return max(0.0, value - threshold) / max(abs(threshold), 1e-30)


def corner_constraint_components(
    metrics: Mapping[str, float | None], statuses: Mapping[str, Any]
) -> dict[str, float]:
    ugf_status = str(statuses.get("ugf_status", "not_run"))
    ugf = _finite(metrics, "ugf_hz")
    ugf_valid = ugf_status == UgfStatus.MEASURED.value
    if ugf_status == UgfStatus.RIGHT_CENSORED.value:
        ugf = _finite(metrics, "ugf_lower_bound_hz")
        ugf_valid = ugf is not None
    return {
        "gain_min": _lower(_finite(metrics, "dc_gain_db"), TASK9_SPECIFICATION.gain_min_db),
        "ugf_min": _lower(ugf, TASK9_SPECIFICATION.ugf_min_hz, ugf_valid),
        "phase_margin_min": _lower(
            _finite(metrics, "phase_margin_deg"),
            TASK9_SPECIFICATION.phase_margin_min_deg,
            statuses.get("phase_margin_status") == PhaseMarginStatus.MEASURED.value,
        ),
        "power_max": _upper(_finite(metrics, "dc_power_w"), TASK9_SPECIFICATION.power_max_w),
        "positive_slew_min": _lower(
            _finite(metrics, "positive_slew_v_per_s"),
            TASK9_SPECIFICATION.positive_slew_min_v_per_s,
            statuses.get("positive_slew_status") == SlewStatus.MEASURED.value,
        ),
        "negative_slew_min": _lower(
            _finite(metrics, "negative_slew_v_per_s"),
            TASK9_SPECIFICATION.negative_slew_min_v_per_s,
            statuses.get("negative_slew_status") == SlewStatus.MEASURED.value,
        ),
        "output_low": _lower(_finite(metrics, "output_dc_voltage"), TASK9_SPECIFICATION.output_min_v),
        "output_high": _upper(_finite(metrics, "output_dc_voltage"), TASK9_SPECIFICATION.output_max_v),
        "operating_region": _lower(_finite(metrics, "operating_region_valid"), 1.0),
    }


STAGE_COMPONENTS = {
    "op": ("operating_region", "power_max", "output_low", "output_high"),
    "ac": ("gain_min", "ugf_min", "phase_margin_min"),
    "transient": ("positive_slew_min", "negative_slew_min"),
}


def stage_decision(
    stage: str,
    metrics: Mapping[str, float | None],
    statuses: Mapping[str, Any],
) -> StageDecision:
    if stage not in STAGE_COMPONENTS:
        raise ValueError(f"unknown Task 9 stage '{stage}'")
    components = corner_constraint_components(metrics, statuses)
    blocker = next(
        (name for name in STAGE_COMPONENTS[stage] if components[name] > 0.0), None
    )
    return StageDecision(blocker is None, stage, blocker)


def robust_objective(corners: Sequence[Mapping[str, Any]]) -> RobustObjective:
    if len(corners) != len(PVT_CORNERS):
        raise ValueError("Full-PVT objective requires all 15 corners")
    components_by_corner = [
        corner_constraint_components(corner["metrics"], corner["statuses"])
        for corner in corners
    ]
    robust = {
        name: max(float(components[name]) for components in components_by_corner)
        for name in CONSTRAINT_NAMES
    }
    violation = sum(robust.values())
    powers = [_finite(corner["metrics"], "dc_power_w") for corner in corners]
    worst_power = None if any(value is None for value in powers) else max(
        float(value) for value in powers if value is not None
    )
    feasible = violation == 0.0 and worst_power is not None
    objective = (
        worst_power / (TASK9_SPECIFICATION.power_max_w + worst_power)
        if feasible and worst_power is not None
        else 1.0 + violation
    )
    return RobustObjective(objective, violation, robust, feasible, worst_power)


def partial_feedback(
    corners: Sequence[Mapping[str, Any]],
    *,
    progress_units: int,
    pvt_feasible: bool = False,
) -> PartialFeedback:
    if not 0 <= progress_units <= MAX_PROGRESS_UNITS:
        raise ValueError("Task 9 progress units must be in [0, 45]")
    measured = [corner for corner in corners if corner.get("started")]
    if not measured:
        components = {name: 0.0 for name in CONSTRAINT_NAMES}
    else:
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
        per_corner = []
        for corner in measured:
            raw = corner_constraint_components(corner["metrics"], corner["statuses"])
            completed = set(corner.get("completed_analyses", ()))
            per_corner.append(
                {
                    name: raw[name] if stage in completed else 0.0
                    for name, stage in component_stage.items()
                }
            )
        components = {
            name: max(float(item[name]) for item in per_corner)
            for name in CONSTRAINT_NAMES
        }
    violation = sum(components.values())
    if pvt_feasible:
        full = robust_objective(corners)
        objective = full.objective_value
        tier = (0, 0, objective)
    else:
        bounded = violation / (1.0 + violation)
        objective = 1.0 + (MAX_PROGRESS_UNITS - progress_units) + bounded
        tier = (1, MAX_PROGRESS_UNITS - progress_units, violation)
    return PartialFeedback(
        objective,
        progress_units,
        violation,
        components,
        pvt_feasible,
        tier,
    )


def worst_corner_summary(corners: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    definitions = {
        "gain": ("dc_gain_db", "min"),
        "ugf": ("ugf_hz", "min"),
        "phase_margin": ("phase_margin_deg", "min"),
        "slew_positive": ("positive_slew_v_per_s", "min"),
        "slew_negative": ("negative_slew_v_per_s", "min"),
        "power": ("dc_power_w", "max"),
    }
    result: dict[str, Any] = {}
    for label, (metric, direction) in definitions.items():
        valid = [
            (corner["corner_id"], _finite(corner["metrics"], metric))
            for corner in corners
            if corner.get("started")
        ]
        valid = [(corner_id, value) for corner_id, value in valid if value is not None]
        if not valid:
            result[f"worst_{label}"] = None
            result[f"worst_corner_for_{label}"] = None
        else:
            selected = min(valid, key=lambda item: item[1]) if direction == "min" else max(valid, key=lambda item: item[1])
            result[f"worst_{label}"] = selected[1]
            result[f"worst_corner_for_{label}"] = selected[0]
    margins = []
    for corner in corners:
        output = _finite(corner["metrics"], "output_dc_voltage")
        if corner.get("started") and output is not None:
            margins.append(
                (
                    corner["corner_id"],
                    min(output - TASK9_SPECIFICATION.output_min_v, TASK9_SPECIFICATION.output_max_v - output),
                )
            )
    if margins:
        selected_margin = min(margins, key=lambda item: item[1])
        result["worst_output_margin"] = selected_margin[1]
        result["worst_corner_for_output_margin"] = selected_margin[0]
    else:
        result["worst_output_margin"] = None
        result["worst_corner_for_output_margin"] = None
    return result


def replay_complete_matrix(
    corners: Sequence[Mapping[str, Any]],
    *,
    order: Sequence[str],
    full_pvt_feasible: bool,
) -> ReplayAudit:
    if len(corners) != len(PVT_CORNERS):
        raise ValueError("Task 9 replay requires a complete 15-corner matrix")
    by_id = {str(corner["corner_id"]): corner for corner in corners}
    if set(by_id) != set(CANONICAL_CORNER_ORDER) or set(order) != set(by_id):
        raise ValueError("Task 9 replay corner identity mismatch")
    op_calls = ac_calls = transient_calls = corners_started = 0
    first_corner = first_stage = first_constraint = None
    for corner_id in order:
        corner = by_id[corner_id]
        corners_started += 1
        op_calls += 1
        decision = stage_decision("op", corner["metrics"], corner["statuses"])
        if not decision.passed:
            first_corner, first_stage, first_constraint = corner_id, "op", decision.first_blocking_constraint
            break
        ac_calls += 1
        decision = stage_decision("ac", corner["metrics"], corner["statuses"])
        if not decision.passed:
            first_corner, first_stage, first_constraint = corner_id, "ac", decision.first_blocking_constraint
            break
        transient_calls += 1
        decision = stage_decision("transient", corner["metrics"], corner["statuses"])
        if not decision.passed:
            first_corner, first_stage, first_constraint = corner_id, "transient", decision.first_blocking_constraint
            break
    replay_feasible = first_corner is None
    return ReplayAudit(
        replay_feasible,
        bool(full_pvt_feasible),
        replay_feasible and not bool(full_pvt_feasible),
        not replay_feasible and bool(full_pvt_feasible),
        corners_started,
        op_calls,
        ac_calls,
        transient_calls,
        first_corner,
        first_stage,
        first_constraint,
    )


def verify_frozen_constants() -> None:
    if stable_hash([corner.to_dict() for corner in PVT_CORNERS]) != CORNER_SUITE_HASH:
        raise RuntimeError("Task 9 corner-suite constants drifted")
    if set(STATIC_WORST_FIRST_ORDER) != set(CANONICAL_CORNER_ORDER):
        raise RuntimeError("Task 9 static order is not a permutation of the suite")


verify_frozen_constants()
