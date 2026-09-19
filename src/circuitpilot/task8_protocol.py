"""Pure, versioned staged-decision semantics for Research Task 8."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

from circuitpilot.sky130_two_stage_ota import PhaseMarginStatus, SlewStatus, UgfStatus
from circuitpilot.task7_protocol import (
    TASK7_BENCHMARK_HASH,
    Task7Specification,
    evaluate_task7_objective,
    stable_hash,
)


EVALUATION_POLICY_VERSION = "task8_op_ac_transient_safe_hierarchy_v1"
PARTIAL_FEEDBACK_VERSION = "task8_hierarchical_lexicographic_feedback_v1"
COST_ACCOUNTING_VERSION = "task8_real_subprocess_elapsed_sum_v1"
BUDGET_SEMANTICS_VERSION = "task8_terminal_candidate_budget_check_v1"
FORMAL_CANDIDATE_BUDGET = 50
FORMAL_SIMULATION_TIME_BUDGET_SECONDS = 90.0
FORMAL_SIMULATION_TIME_CANDIDATE_CAP = 300

TASK8_SPECIFICATION = Task7Specification(
    gain_min_db=12.0,
    ugf_min_hz=5.0e5,
    phase_margin_min_deg=35.0,
    power_max_w=1.5e-3,
    positive_slew_min_v_per_s=5.0e5,
    negative_slew_min_v_per_s=5.0e5,
    output_min_v=0.10,
    output_max_v=1.70,
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


@dataclass(frozen=True, slots=True)
class StageDecision:
    """Deterministic result from one frozen stage gate."""

    passed: bool
    evaluation_stage: str
    first_blocking_constraint: str | None
    violation_sum: float


@dataclass(frozen=True, slots=True)
class ReplayDecision:
    """Counterfactual Task 8 stopping decision over frozen Full evidence."""

    evaluation_stage: str
    first_blocking_constraint: str | None
    op_calls: int
    ac_calls: int
    transient_calls: int
    false_rejection: bool

    @property
    def process_calls(self) -> int:
        return self.op_calls + self.ac_calls + self.transient_calls


def evaluation_policy_hash(policy: str) -> str:
    if policy not in {"full", "hierarchical"}:
        raise ValueError("Task 8 policy must be full or hierarchical")
    return stable_hash(
        {
            "version": EVALUATION_POLICY_VERSION,
            "policy": policy,
            "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
            "specification": TASK8_SPECIFICATION.to_dict(),
            "stage_order": ["op", "ac", "transient"],
            "first_blocker_priority": {
                "op": ["operating_region", "power", "output_bias"],
                "ac": ["gain", "ugf", "phase_margin"],
                "transient": ["positive_slew", "negative_slew"],
            },
            "unknown_metric": None,
        }
    )


EVALUATION_STAGE_SEMANTICS_HASH = stable_hash(
    {
        "version": EVALUATION_POLICY_VERSION,
        "terminal_stages": [
            "op_rejected",
            "ac_rejected",
            "transient_rejected",
            "full_infeasible",
            "fully_feasible",
            "analysis_failed",
        ],
    }
)
PARTIAL_FEEDBACK_SEMANTICS_HASH = stable_hash(
    {
        "version": PARTIAL_FEEDBACK_VERSION,
        "tiers": {
            "fully_feasible": 0,
            "transient_rejected": 1,
            "ac_rejected": 2,
            "op_rejected": 3,
        },
        "bounded_violation": "v/(1+v)",
        "full_policy": "unchanged_task7_objective",
    }
)
SIMULATION_TIME_BUDGET_HASH = stable_hash(
    {
        "version": BUDGET_SEMANTICS_VERSION,
        "budget_seconds": FORMAL_SIMULATION_TIME_BUDGET_SECONDS,
        "candidate_cap": FORMAL_SIMULATION_TIME_CANDIDATE_CAP,
        "check": "after_candidate_terminal",
        "inflight": "complete_required_policy_chain",
    }
)
COST_ACCOUNTING_HASH = stable_hash(
    {
        "version": COST_ACCOUNTING_VERSION,
        "primary": "sum_ngspice_subprocess_elapsed_seconds",
        "secondary": ["outer_wall_seconds", "orchestration_seconds"],
        "shadow_cost": "separate_and_excluded",
    }
)


def _required(metrics: Mapping[str, float | None], name: str) -> float:
    value = metrics.get(name)
    if value is None or not isfinite(float(value)):
        raise ValueError(f"required measured metric '{name}' is unavailable")
    return float(value)


def _lower(value: float, threshold: float) -> float:
    return max(0.0, threshold - value) / max(abs(threshold), 1e-30)


def _upper(value: float, threshold: float) -> float:
    return max(0.0, value - threshold) / max(abs(threshold), 1e-30)


def op_gate(metrics: Mapping[str, float | None]) -> StageDecision:
    operating_region = _required(metrics, "operating_region_valid")
    power = _required(metrics, "dc_power_w")
    output = _required(metrics, "output_dc_voltage")
    components = {
        "operating_region": max(0.0, 1.0 - operating_region),
        "power": _upper(power, TASK8_SPECIFICATION.power_max_w),
        "output_low": _lower(output, TASK8_SPECIFICATION.output_min_v),
        "output_high": _upper(output, TASK8_SPECIFICATION.output_max_v),
    }
    violation = sum(components.values())
    blocker = None
    if components["operating_region"] > 0:
        blocker = "operating_region"
    elif components["power"] > 0:
        blocker = "power"
    elif components["output_low"] > 0 or components["output_high"] > 0:
        blocker = "output_bias"
    return StageDecision(
        passed=blocker is None,
        evaluation_stage="op_passed" if blocker is None else "op_rejected",
        first_blocking_constraint=blocker,
        violation_sum=violation,
    )


def ac_gate(
    metrics: Mapping[str, float | None],
    *,
    ugf_status: str,
    phase_margin_status: str,
) -> StageDecision:
    gain = _required(metrics, "dc_gain_db")
    gain_violation = _lower(gain, TASK8_SPECIFICATION.gain_min_db)

    ugf_value: float | None = None
    if ugf_status == UgfStatus.MEASURED.value:
        ugf_value = metrics.get("ugf_hz")
    elif ugf_status == UgfStatus.RIGHT_CENSORED.value:
        ugf_value = metrics.get("ugf_lower_bound_hz")
    ugf_violation = (
        1.0
        if ugf_value is None
        else _lower(float(ugf_value), TASK8_SPECIFICATION.ugf_min_hz)
    )

    phase_value = metrics.get("phase_margin_deg")
    phase_valid = (
        phase_margin_status == PhaseMarginStatus.MEASURED.value
        and phase_value is not None
    )
    phase_violation = (
        _lower(float(phase_value), TASK8_SPECIFICATION.phase_margin_min_deg)
        if phase_valid
        else 1.0
    )
    violation = gain_violation + ugf_violation + phase_violation
    blocker = None
    if gain_violation > 0:
        blocker = "gain"
    elif ugf_violation > 0:
        blocker = "ugf"
    elif phase_violation > 0:
        blocker = "phase_margin"
    return StageDecision(
        passed=blocker is None,
        evaluation_stage="ac_passed" if blocker is None else "ac_rejected",
        first_blocking_constraint=blocker,
        violation_sum=violation,
    )


def transient_gate(
    metrics: Mapping[str, float | None],
    *,
    positive_slew_status: str,
    negative_slew_status: str,
) -> StageDecision:
    positive = metrics.get("positive_slew_v_per_s")
    negative = metrics.get("negative_slew_v_per_s")
    positive_violation = (
        _lower(float(positive), TASK8_SPECIFICATION.positive_slew_min_v_per_s)
        if positive_slew_status == SlewStatus.MEASURED.value and positive is not None
        else 1.0
    )
    negative_violation = (
        _lower(float(negative), TASK8_SPECIFICATION.negative_slew_min_v_per_s)
        if negative_slew_status == SlewStatus.MEASURED.value and negative is not None
        else 1.0
    )
    violation = positive_violation + negative_violation
    blocker = None
    if positive_violation > 0:
        blocker = "positive_slew"
    elif negative_violation > 0:
        blocker = "negative_slew"
    return StageDecision(
        passed=blocker is None,
        evaluation_stage="fully_feasible" if blocker is None else "transient_rejected",
        first_blocking_constraint=blocker,
        violation_sum=violation,
    )


def hierarchical_objective(
    stage: str,
    violation_sum: float,
    metrics: Mapping[str, float | None],
    *,
    ugf_status: str,
    phase_margin_status: str,
    positive_slew_status: str,
    negative_slew_status: str,
) -> float:
    if stage == "fully_feasible":
        result = evaluate_task7_objective(
            metrics,
            TASK8_SPECIFICATION,
            ugf_status=ugf_status,
            phase_margin_status=phase_margin_status,
            positive_slew_status=positive_slew_status,
            negative_slew_status=negative_slew_status,
        )
        if not result.is_feasible:
            raise ValueError("fully_feasible stage does not satisfy Task 7")
        return result.objective_value
    tiers = {"transient_rejected": 1.0, "ac_rejected": 2.0, "op_rejected": 3.0}
    if stage not in tiers or not isfinite(violation_sum) or violation_sum <= 0:
        raise ValueError("invalid Task 8 partial-feedback input")
    return tiers[stage] + violation_sum / (1.0 + violation_sum)


def replay_decision(
    metrics: Mapping[str, float | None],
    *,
    ugf_status: str,
    phase_margin_status: str,
    positive_slew_status: str,
    negative_slew_status: str,
    full_is_feasible: bool,
) -> ReplayDecision:
    op = op_gate(metrics)
    if not op.passed:
        return ReplayDecision(
            "op_rejected",
            op.first_blocking_constraint,
            1,
            0,
            0,
            bool(full_is_feasible),
        )
    ac = ac_gate(
        metrics,
        ugf_status=ugf_status,
        phase_margin_status=phase_margin_status,
    )
    if not ac.passed:
        return ReplayDecision(
            "ac_rejected",
            ac.first_blocking_constraint,
            1,
            1,
            0,
            bool(full_is_feasible),
        )
    transient = transient_gate(
        metrics,
        positive_slew_status=positive_slew_status,
        negative_slew_status=negative_slew_status,
    )
    return ReplayDecision(
        transient.evaluation_stage,
        transient.first_blocking_constraint,
        1,
        1,
        1,
        False,
    )
