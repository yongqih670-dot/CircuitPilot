"""Frozen Task 6 protocol definitions and stable evaluation-policy hashes."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any

from circuitpilot.task6_physics import (
    OFF_MARGIN_V,
    OP_FEEDBACK_SEMANTICS_VERSION,
    OUTPUT_HIGH_V,
    OUTPUT_LOW_V,
    PHYSICS_RULES_VERSION,
    REJECTED_OBJECTIVE_BASE,
    VIOLATION_BITS,
)


TASK5_BENCHMARK_HASH = (
    "57d2183621ecf37e5ca22e012452c43fce6459be7d347a5cfc93d0b394c14378"
)
FULL_POLICY = "full"
SCREENED_POLICY = "op_screened"
FULL_POLICY_VERSION = "task6_full_task5_reproduction_v1"
SCREENED_POLICY_VERSION = "task6_op_screened_two_stage_v1"
COST_MODEL_VERSION = "task6_logical_ac_primary_cost_v1"
WALL_TIME_POLICY = "measured_not_stopping_v1"
STATISTICAL_PLAN_VERSION = "task6_paired_survival_effects_v1"
SMOKE_CANDIDATE_CAP = 25
FORMAL_CANDIDATE_CAP = 100
COST_BUDGET_CANDIDATE_CAP = 300
EXPENSIVE_AC_BUDGET = 200
FORMAL_SEEDS = tuple(range(10))
SMOKE_SEEDS = (0, 1, 2)
METHODS = ("random", "de", "tpe", "bo")


def stable_hash(value: Any) -> str:
    """Hash a JSON-compatible semantic definition canonically."""
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def physics_rule_definition() -> dict[str, Any]:
    return {
        "version": PHYSICS_RULES_VERSION,
        "nmos_overdrive": "vgs-vth",
        "pmos_overdrive": "abs(vgs)-abs(vth)",
        "off": "overdrive<=0",
        "not_saturated": "on and drain_headroom<overdrive",
        "output_valid_inclusive_v": [OUTPUT_LOW_V, OUTPUT_HIGH_V],
        "off_margin_v": OFF_MARGIN_V,
        "violation_bits": dict(VIOLATION_BITS),
        "multiple_label": "derived_when_primary_count_gt_1",
    }


def op_feedback_definition() -> dict[str, Any]:
    return {
        "version": OP_FEEDBACK_SEMANTICS_VERSION,
        "device_off_deficit": (
            "max(0,off_margin-overdrive)/max(abs(vth),1e-3)"
        ),
        "device_saturation_deficit": (
            "0_if_off_else_max(0,overdrive-drain_headroom)"
            "/max(overdrive,1e-3)"
        ),
        "output_deficit": (
            "(max(0,0.25-vout)+max(0,vout-1.55))/1.30"
        ),
        "op_constraint_violation": "mean_of_five_devices_and_output",
        "rejected_objective_base": REJECTED_OBJECTIVE_BASE,
        "rejected_objective": "base+violation/(1+violation)",
        "ac_metrics_for_rejected": None,
        "task5_feasibility_unchanged": True,
    }


def cost_model_definition() -> dict[str, Any]:
    return {
        "version": COST_MODEL_VERSION,
        "primary_expensive_cost": (
            "differential_ac_calls+common_mode_ac_calls"
        ),
        "full": {
            "processes": 1,
            "dc_op_calls": 1,
            "differential_ac_calls": 1,
            "common_mode_ac_calls": 1,
            "physical_analysis_calls": 2,
        },
        "screened_rejected": {
            "processes": 1,
            "dc_op_calls": 1,
            "differential_ac_calls": 0,
            "common_mode_ac_calls": 0,
            "physical_analysis_calls": 1,
        },
        "screened_full": {
            "processes": 2,
            "dc_op_calls": 1,
            "differential_ac_calls": 1,
            "common_mode_ac_calls": 1,
            "physical_analysis_calls": 2,
        },
        "wall_time_policy": WALL_TIME_POLICY,
    }


def policy_definition(policy: str) -> dict[str, Any]:
    """Return the semantics whose hash distinguishes the experiment variable."""
    if policy not in {FULL_POLICY, SCREENED_POLICY}:
        raise ValueError("evaluation policy must be full or op_screened")
    return {
        "task5_benchmark_hash": TASK5_BENCHMARK_HASH,
        "evaluation_policy": policy,
        "evaluation_policy_version": (
            FULL_POLICY_VERSION
            if policy == FULL_POLICY
            else SCREENED_POLICY_VERSION
        ),
        "stage_definition": (
            "one_process_task5_op_plus_combined_dual_ac"
            if policy == FULL_POLICY
            else "explicit_op_then_conditional_combined_dual_ac"
        ),
        "physics_rules_hash": stable_hash(physics_rule_definition()),
        "op_feedback_semantics_hash": stable_hash(op_feedback_definition()),
        "cost_model_hash": stable_hash(cost_model_definition()),
    }


def evaluation_policy_hash(policy: str) -> str:
    return stable_hash(policy_definition(policy))


def evaluation_policy_family_hash() -> str:
    return stable_hash(
        {
            "policies": {
                policy: policy_definition(policy)
                for policy in (FULL_POLICY, SCREENED_POLICY)
            },
            "methods": list(METHODS),
            "smoke": {
                "seeds": list(SMOKE_SEEDS),
                "candidate_cap": SMOKE_CANDIDATE_CAP,
            },
            "equal_candidate": {
                "seeds": list(FORMAL_SEEDS),
                "candidate_cap": FORMAL_CANDIDATE_CAP,
            },
            "equal_cost": {
                "seeds": list(FORMAL_SEEDS),
                "candidate_cap": COST_BUDGET_CANDIDATE_CAP,
                "expensive_ac_budget": EXPENSIVE_AC_BUDGET,
            },
            "statistics": STATISTICAL_PLAN_VERSION,
        }
    )
