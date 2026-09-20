"""Freeze Task 9 benchmark and policy identities before implementation."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from circuitpilot.task7_protocol import (  # noqa: E402
    METHODS,
    TASK7_BENCHMARK_HASH,
    TASK7_COMPONENT_HASHES,
    TASK7_FROZEN_YAML_BYTE_HASH,
    TASK7_SEARCH_SPACE_HASH,
    stable_hash,
)


ROOT = PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task9"
TASK7_YAML = PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task7_frozen.yaml"
TASK8_MANIFEST = PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task8" / "task8_protocol_manifest.json"
FROZEN_DOCUMENTS = (
    "PVT_MODEL_CAPABILITY_REPORT.md",
    "PVT_CORNER_PROTOCOL.md",
    "PVT_SPECIFICATION_LADDER.yaml",
    "PVT_SPECIFICATION_LADDER_ERRATUM.md",
    "RESEARCH_HYPOTHESES.md",
    "STATISTICAL_ANALYSIS_PLAN.md",
    "NOMINAL_TO_PVT_GAP_REPORT.md",
    "PVT_CALIBRATION_PROTOCOL.md",
    "CALIBRATION_SPECIFICATION_SELECTION.md",
    "STATIC_CORNER_ORDER.md",
    "REPLAY_EQUIVALENCE_REPORT.md",
    "PVT_OTA_BENCHMARK.md",
    "PVT_EVALUATION_POLICY.md",
    "PVT_FEEDBACK_SEMANTICS.md",
)


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def main() -> int:
    task7 = yaml.safe_load(TASK7_YAML.read_text(encoding="utf-8"))
    task8 = json.loads(TASK8_MANIFEST.read_text(encoding="utf-8"))
    selected = json.loads((ROOT / "calibration" / "selected_specification.json").read_text(encoding="utf-8"))
    order = json.loads((ROOT / "calibration" / "static_corner_order.json").read_text(encoding="utf-8"))
    calibration_candidates = json.loads((ROOT / "calibration" / "calibration_candidates.json").read_text(encoding="utf-8"))
    replay = json.loads((ROOT / "replay" / "replay_summary.json").read_text(encoding="utf-8"))
    document_hashes = {name: file_sha256(ROOT / name) for name in FROZEN_DOCUMENTS}
    corners = [
        {
            "corner_id": f"{process}__{condition}",
            "process_corner": process,
            "condition": condition,
            "vdd_v": vdd,
            "temperature_c": temperature,
        }
        for process in ("tt", "ss", "ff", "fs", "sf")
        for condition, vdd, temperature in (
            ("nominal", 1.80, 27.0),
            ("low_v_high_t", 1.62, 125.0),
            ("high_v_low_t", 1.98, -40.0),
        )
    ]
    corner_suite_hash = stable_hash(corners)
    if corner_suite_hash != json.loads(
        (ROOT / "calibration" / "full_pvt" / "summary.json").read_text(encoding="utf-8")
    )["corner_suite_hash"]:
        raise RuntimeError("corner-suite identity differs from calibration")
    circuit = task7["circuit_config"]
    benchmark_identity: dict[str, Any] = {
        "version": "task9_pvt_ota_benchmark_v1",
        "task7": {
            "benchmark_hash": TASK7_BENCHMARK_HASH,
            "frozen_yaml_sha256": TASK7_FROZEN_YAML_BYTE_HASH,
            "search_space_hash": TASK7_SEARCH_SPACE_HASH,
            "component_hashes": TASK7_COMPONENT_HASHES,
            "search_space": task7["search_space"],
            "topology_version": circuit["topology_version"],
            "device_role_mapping_version": circuit["device_role_mapping_version"],
            "model": circuit["sky130_model"],
            "measurement_semantics": {
                name: circuit[name]
                for name in (
                    "ac_testbench_version",
                    "ugf_semantics_version",
                    "phase_margin_semantics_version",
                    "transient_testbench_version",
                    "slew_semantics_version",
                    "op_rules_version",
                    "cost_semantics_version",
                )
            },
            "fixed_testbench": {
                name: circuit[name]
                for name in (
                    "input_common_mode_v",
                    "tail_bias_v",
                    "load_capacitance_f",
                    "transient_low_v",
                    "transient_high_v",
                    "transient_rise_time_s",
                    "transient_fall_time_s",
                    "transient_rising_edge_s",
                    "transient_falling_edge_s",
                    "transient_stop_time_s",
                    "transient_max_step_s",
                    "transient_edge_exclusion_s",
                    "slew_lower_fraction",
                    "slew_upper_fraction",
                )
            },
            "ngspice_config": task7["ngspice_config"],
        },
        "task8_protocol_hash": task8["task8_protocol_hash"],
        "corner_suite": corners,
        "corner_suite_hash": corner_suite_hash,
        "selected_specification_row": selected["selected_row"],
        "selected_specification": selected["selected_constraints"],
        "selected_specification_hash": selected["selected_specification_hash"],
        "corner_order": order["static_worst_first_order"],
        "corner_order_hash": order["corner_order_hash"],
        "objective": {
            "feasibility": "logical_and_all_constraints_all_corners_valid_statuses",
            "robust_violation": "sum_constraints_of_max_corner_normalized_violation",
            "feasible_secondary": "minimize_max_corner_dc_power_w",
            "universal_worst_corner": False,
        },
        "methods": list(METHODS),
        "formal_seeds": list(range(10)),
        "smoke_seeds": [0, 1, 2],
        "calibration_candidate_set_hash": calibration_candidates["candidate_set_hash"],
        "protocol_document_hashes": document_hashes,
    }
    pvt_benchmark_hash = stable_hash(benchmark_identity)
    full_policy = {
        "name": "PVTFullEvaluationPolicy",
        "version": "task9_full_all_corners_all_stages_v1",
        "benchmark_hash": pvt_benchmark_hash,
        "corner_order": [corner["corner_id"] for corner in corners],
        "always_attempt_all_corners": True,
        "always_attempt_stages": ["op", "ac", "transient"],
        "isolated_failures": True,
    }
    hierarchy_policy = {
        "name": "PVTHierarchicalEvaluationPolicy",
        "version": "task9_safe_stage_and_corner_hierarchy_v1",
        "benchmark_hash": pvt_benchmark_hash,
        "corner_order": order["static_worst_first_order"],
        "corner_order_hash": order["corner_order_hash"],
        "stage_order": ["op", "ac", "transient"],
        "first_blocker_priority": {
            "op": ["operating_region", "power_max", "output_low", "output_high"],
            "ac": ["gain_min", "ugf_min", "phase_margin_min"],
            "transient": ["positive_slew_min", "negative_slew_min"],
        },
        "across_corner_stop": "first_measured_hard_failure_or_invalid_required_measurement",
        "unknown_physical_metric": None,
        "prediction": False,
        "adaptive_order": False,
    }
    full_policy_hash = stable_hash(full_policy)
    hierarchical_policy_hash = stable_hash(hierarchy_policy)
    evaluation_policy_identity = {
        "version": "task9_pvt_evaluation_policy_family_v1",
        "benchmark_hash": pvt_benchmark_hash,
        "full_policy_hash": full_policy_hash,
        "hierarchical_policy_hash": hierarchical_policy_hash,
        "replay_gate": {
            "passed": replay["gate_passed"],
            "false_acceptance": 0,
            "false_rejection": 0,
        },
    }
    pvt_evaluation_policy_hash = stable_hash(evaluation_policy_identity)
    feedback_identity = {
        "version": "task9_measured_progress_lexicographic_feedback_v1",
        "benchmark_hash": pvt_benchmark_hash,
        "tiers": "pvt_feasible_then_progress_units_then_partial_violation",
        "progress_units_max": 45,
        "infeasible_scalar": "1+(45-progress)+V/(1+V)",
        "feasible_scalar": "worst_power/(power_limit+worst_power)",
        "unrun_metric": None,
    }
    partial_feedback_hash = stable_hash(feedback_identity)
    cost_identity = {
        "version": "task9_real_subprocess_elapsed_sum_v1",
        "primary": "sum_ngspice_subprocess_elapsed_seconds",
        "counts": [
            "candidate_count",
            "corners_started",
            "corners_completed",
            "op_calls",
            "ac_calls",
            "transient_calls",
            "process_calls",
        ],
        "shadow_excluded": True,
    }
    cost_accounting_hash = stable_hash(cost_identity)
    budget_identity = {
        "version": "task9_terminal_analysis_budget_check_v1",
        "equal_candidate_budget": selected["formal_equal_candidate_budget"],
        "equal_time_budget_seconds": selected["formal_equal_time_budget_seconds"],
        "equal_time_candidate_cap": selected["formal_equal_time_candidate_cap"],
        "smoke_candidate_budget": selected["smoke_candidate_budget"],
        "budget_check": "after_completed_analysis_never_kill_process",
    }
    budget_hash = stable_hash(budget_identity)
    hashes = {
        "pvt_benchmark_hash": pvt_benchmark_hash,
        "corner_suite_hash": corner_suite_hash,
        "corner_order_hash": order["corner_order_hash"],
        "pvt_evaluation_policy_hash": pvt_evaluation_policy_hash,
        "full_policy_hash": full_policy_hash,
        "hierarchical_policy_hash": hierarchical_policy_hash,
        "partial_feedback_hash": partial_feedback_hash,
        "cost_accounting_hash": cost_accounting_hash,
        "simulation_time_budget_hash": budget_hash,
    }
    hashes["task9_protocol_hash"] = stable_hash(hashes)
    frozen = {
        "schema_version": "task9_pvt_ota_frozen_v1",
        "freeze_parent_commit": git_head(),
        "hashes": hashes,
        "benchmark": benchmark_identity,
        "policies": {"full": full_policy, "hierarchical": hierarchy_policy},
        "feedback": feedback_identity,
        "cost_accounting": cost_identity,
        "budgets": budget_identity,
    }
    (ROOT / "task9_pvt_ota_frozen.yaml").write_text(
        yaml.safe_dump(frozen, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    manifest = {
        "schema_version": "task9_protocol_manifest_v1",
        "freeze_parent_commit": frozen["freeze_parent_commit"],
        "hashes": hashes,
        "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
        "task8_protocol_hash": task8["task8_protocol_hash"],
        "selected_specification_row": selected["selected_row"],
        "calibration_density": selected["selected_density"],
        "calibration_target_achieved": selected["target_band_achieved"],
        "calibration_candidate_set_hash": calibration_candidates["candidate_set_hash"],
        "replay_gate_passed": replay["gate_passed"],
        "frozen_document_hashes": document_hashes,
        "frozen_yaml_sha256": None,
    }
    frozen_hash = file_sha256(ROOT / "task9_pvt_ota_frozen.yaml")
    manifest["frozen_yaml_sha256"] = frozen_hash
    (ROOT / "task9_protocol_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    freeze_report = "# Task 9 Protocol Freeze\n\n" + "\n".join(
        f"- {name}: `{value}`" for name, value in hashes.items()
    )
    freeze_report += (
        f"\n- frozen YAML byte SHA-256: `{frozen_hash}`\n"
        f"- freeze parent commit: `{frozen['freeze_parent_commit']}`\n\n"
        "All protocol documents were hashed before evaluator implementation. "
        "The manifest records their byte identities.\n"
    )
    (ROOT / "TASK9_PROTOCOL_FREEZE.md").write_text(freeze_report, encoding="utf-8")
    print(json.dumps({**hashes, "frozen_yaml_sha256": frozen_hash}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
