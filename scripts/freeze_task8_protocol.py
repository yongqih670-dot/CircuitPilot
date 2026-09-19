"""Freeze the pre-formal Task 8 protocol and evidence identities."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
from typing import Any

from circuitpilot.task7_protocol import (
    METHODS,
    TASK7_BENCHMARK_HASH,
    TASK7_COMPONENT_HASHES,
    TASK7_FROZEN_YAML_BYTE_HASH,
    TASK7_SEARCH_SPACE_HASH,
    stable_hash,
)
from circuitpilot.task8_protocol import (
    COST_ACCOUNTING_HASH,
    EVALUATION_STAGE_SEMANTICS_HASH,
    FORMAL_CANDIDATE_BUDGET,
    FORMAL_SIMULATION_TIME_BUDGET_SECONDS,
    FORMAL_SIMULATION_TIME_CANDIDATE_CAP,
    PARTIAL_FEEDBACK_SEMANTICS_HASH,
    SIMULATION_TIME_BUDGET_HASH,
    evaluation_policy_hash,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK8_ROOT = (
    PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task8"
)
FREEZE_INPUTS = (
    TASK8_ROOT / "TASK7_FREEZE_AUDIT.md",
    TASK8_ROOT / "RESEARCH_HYPOTHESES.md",
    TASK8_ROOT / "EVALUATION_POLICY.md",
    TASK8_ROOT / "PARTIAL_FEEDBACK_SEMANTICS.md",
    TASK8_ROOT / "COST_MODEL.md",
    TASK8_ROOT / "STATISTICAL_ANALYSIS_PLAN.md",
    TASK8_ROOT / "REPLAY_EQUIVALENCE_REPORT.md",
    TASK8_ROOT / "ANALYSIS_COST_PROFILE.md",
    TASK8_ROOT / "results" / "replay" / "summary.json",
    TASK8_ROOT / "results" / "replay" / "staged_replay.csv",
    TASK8_ROOT / "results" / "cost_profile" / "summary.json",
    TASK8_ROOT / "results" / "cost_profile" / "cost_profile.csv",
    PROJECT_ROOT / "src" / "circuitpilot" / "task8_protocol.py",
)


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    return str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")


def build_manifest() -> dict[str, Any]:
    missing = [_relative(path) for path in FREEZE_INPUTS if not path.is_file()]
    if missing:
        raise RuntimeError(f"Task 8 freeze inputs are missing: {missing}")
    replay = json.loads(
        (TASK8_ROOT / "results" / "replay" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    if replay["false_rejection_count"] != 0 or replay["candidate_count"] != 2000:
        raise RuntimeError("Task 8 replay gate is not a zero-false-rejection pass")
    cost = json.loads(
        (TASK8_ROOT / "results" / "cost_profile" / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    medians = {
        mode: cost["statistics"][mode]["accumulated_ngspice_seconds"]["median"]
        for mode in ("op_only", "op_ac", "full")
    }
    if not medians["op_only"] < medians["op_ac"] < medians["full"]:
        raise RuntimeError("Task 8 cost profile did not preserve the staged ordering")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        text=True,
        encoding="utf-8",
    ).strip()
    payload: dict[str, Any] = {
        "schema_version": 1,
        "protocol_version": "task8_frozen_hierarchical_ota_v1",
        "frozen_at_source_commit": commit,
        "task7_benchmark_hash": TASK7_BENCHMARK_HASH,
        "task7_search_space_hash": TASK7_SEARCH_SPACE_HASH,
        "task7_frozen_yaml_byte_hash": TASK7_FROZEN_YAML_BYTE_HASH,
        "task7_component_hashes": TASK7_COMPONENT_HASHES,
        "methods": list(METHODS),
        "seeds": list(range(10)),
        "policies": ["full", "hierarchical"],
        "smoke_seeds": [0, 1, 2],
        "smoke_candidate_budget": 25,
        "formal_candidate_budget": FORMAL_CANDIDATE_BUDGET,
        "formal_simulation_time_budget_seconds": (
            FORMAL_SIMULATION_TIME_BUDGET_SECONDS
        ),
        "formal_simulation_time_candidate_cap": (
            FORMAL_SIMULATION_TIME_CANDIDATE_CAP
        ),
        "full_policy_hash": evaluation_policy_hash("full"),
        "hierarchical_policy_hash": evaluation_policy_hash("hierarchical"),
        "evaluation_stage_semantics_hash": EVALUATION_STAGE_SEMANTICS_HASH,
        "partial_feedback_semantics_hash": PARTIAL_FEEDBACK_SEMANTICS_HASH,
        "simulation_time_budget_hash": SIMULATION_TIME_BUDGET_HASH,
        "cost_accounting_hash": COST_ACCOUNTING_HASH,
        "replay_false_rejection_count": replay["false_rejection_count"],
        "cost_profile_median_accumulated_ngspice_seconds": medians,
        "frozen_file_hashes": {
            _relative(path): _hash(path) for path in FREEZE_INPUTS
        },
    }
    payload["task8_protocol_hash"] = stable_hash(payload)
    return payload


def write_outputs(manifest: dict[str, Any]) -> None:
    manifest_path = TASK8_ROOT / "task8_protocol_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    report = f"""# Task 8 Frozen Protocol

Status: frozen after replay and cost profiling, before evaluator implementation.

- Task 8 protocol hash: {manifest["task8_protocol_hash"]}
- frozen source commit: {manifest["frozen_at_source_commit"]}
- Task 7 benchmark hash: {manifest["task7_benchmark_hash"]}
- replay candidates: 2000
- replay false rejections: {manifest["replay_false_rejection_count"]}
- methods: Random, DE, TPE, BO
- policies: Full, Hierarchical
- formal seeds: 0–9
- equal-candidate budget: {manifest["formal_candidate_budget"]}
- equal-time budget: {manifest["formal_simulation_time_budget_seconds"]:.1f} accumulated ngspice seconds
- equal-time candidate cap: {manifest["formal_simulation_time_candidate_cap"]}

## Frozen semantic hashes

| Component | SHA-256 |
|---|---|
| Full evaluation policy | {manifest["full_policy_hash"]} |
| Hierarchical evaluation policy | {manifest["hierarchical_policy_hash"]} |
| evaluation stages | {manifest["evaluation_stage_semantics_hash"]} |
| partial feedback | {manifest["partial_feedback_semantics_hash"]} |
| simulation-time budget | {manifest["simulation_time_budget_hash"]} |
| cost accounting | {manifest["cost_accounting_hash"]} |

The byte identities of every preregistration document, replay output, cost
profile summary/table, and pure policy implementation are stored in
task8_protocol_manifest.json. Formal execution must abort if any identity
changes.
"""
    (TASK8_ROOT / "TASK8_PROTOCOL_FREEZE.md").write_text(
        report, encoding="utf-8"
    )


def main() -> int:
    manifest = build_manifest()
    write_outputs(manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
