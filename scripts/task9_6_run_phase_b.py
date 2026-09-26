"""Approved bounded Task 9.6 Phase B; no Task 10 or v3 execution."""

from __future__ import annotations

import argparse
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import random
import subprocess
import sys
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments.optimizers.differential_evolution import DifferentialEvolutionOptimizer
from circuitpilot.experiments.seeding import initialize_seeds
from circuitpilot.simulator import resolve_ngspice_executable
from circuitpilot.task9_protocol import CONSTRAINT_NAMES
from circuitpilot.task9_6_budget import BudgetExhausted, BudgetLedger
from circuitpilot.task9_6_local_diagnostic import (
    evaluate_task9_6_v2_local_diagnostic, run_diagnostic_op,
)
from circuitpilot.task9_6_sensitivity import from_normalized, normalized_position
from circuitpilot.task9_6_v2_evaluator import (
    FROZEN_TASK7_CONFIG, canonicalize_v2_parameters,
    evaluate_task9_6_benchmark_v2_candidate,
)


OUT = ROOT / "research_runs/task9_6_phase_b"
TRACKED = ROOT / "research/sky130/two_stage_ota/task9_6"
AUTH = TRACKED / "phase_b_authorization.json"
PROPOSALS = TRACKED / "sensitivity_candidates.json"
NEAR = TRACKED / "near_corner_selection.json"
BEST = ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/refinement_analysis.json"
ACTIVITY = {
    "audit": "device_audit_probes", "baseline": "fresh_baseline_full",
    "sensitivity": "sensitivity_48_candidates",
    "search": "hierarchical_search_96_candidates",
    "promotion": "full_promotion_8_candidates",
    "confirmation": "fresh_witness_full_confirmation",
    "positive_hierarchy": "positive_hierarchical_validation",
    "neighborhood": "six_neighbor_full_and_hierarchical",
}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True,
                                    allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parameter_hash(parameters: dict) -> str:
    return sha256(json.dumps(parameters, sort_keys=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def archive_activity(name: str, root: Path, *, command: str) -> dict:
    """Local-only CRC-checked archive; source dir is retained, never deleted."""
    destination = OUT / "archives" / f"{name}.zip"
    if destination.exists():
        raise FileExistsError(f"refusing to replace evidence archive: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in root.rglob("*") if path.is_file())
    with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=6) as zipfile:
        for path in files:
            zipfile.write(path, path.relative_to(OUT).as_posix())
    with ZipFile(destination) as zipfile:
        if zipfile.testzip() is not None:
            raise RuntimeError("raw evidence archive CRC failed")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                     text=True).strip()
    payload = {
        "schema_version": "task9_6_evidence_archive_v1",
        "archive_path": str(destination.relative_to(ROOT)).replace("\\", "/"),
        "bytes": destination.stat().st_size,
        "sha256": sha256(destination.read_bytes()).hexdigest(),
        "source_files": len(files), "source_bytes": sum(path.stat().st_size for path in files),
        "associated_commit": commit, "reproduction_command": command,
        "crc_verified": True,
    }
    write_json(TRACKED / "archives" / f"{name}.json", payload)
    return payload


def evaluate_full_or_hierarchy(parameters: dict, *, mode: str, activity: str,
                               name: str, ledger: BudgetLedger, executable: str) -> dict:
    ledger.require_capacity(activity, processes=45 if mode == "full" else 1)
    result_path = OUT / name / "evaluation.json"
    if result_path.exists():
        raise FileExistsError(f"refusing cached/replaced candidate: {result_path}")
    before = ledger.process_count
    with ledger.meter(activity, name):
        result = evaluate_task9_6_benchmark_v2_candidate(
            parameters=parameters, evaluation_directory=OUT / name / "raw",
            executable=executable, mode=mode)
    actual = ledger.process_count - before
    if actual != result["raw_v2_result"]["process_calls"]:
        raise RuntimeError(f"unmetered or nonstarted v2 stage: ledger {actual}, wrapper {result['raw_v2_result']['process_calls']}")
    write_json(result_path, result)
    return result


def phase_audit(ledger: BudgetLedger, executable: str) -> None:
    if (OUT / "baseline/evaluation.json").exists():
        raise FileExistsError("baseline already evaluated")
    original = read_json(BEST)["best_parameters"]
    baseline, roundoff = canonicalize_v2_parameters(original)
    result = evaluate_full_or_hierarchy(baseline, mode="full",
        activity=ACTIVITY["baseline"], name="baseline", ledger=ledger,
        executable=executable)
    failed = [row["corner_id"] for row in result["raw_v2_result"]["corners"]
              if any(value > 0 for value in row["constraint_components"].values())]
    frozen_failed = ["ss__high_v_low_t", "fs__nominal", "fs__high_v_low_t"]
    if sorted(failed) != sorted(frozen_failed):
        print(f"Fresh failure set changed: {failed}; frozen audit still uses {frozen_failed}", flush=True)
    probes = {}
    for corner_id in frozen_failed:
        ledger.require_capacity(ACTIVITY["audit"])
        try:
            probes[corner_id] = run_diagnostic_op(
                parameters=baseline, corner_id=corner_id,
                directory=OUT / "audit" / corner_id, executable=executable,
                ledger=ledger, activity=ACTIVITY["audit"], candidate_id="best12")
        except Exception as exc:
            probes[corner_id] = {"process_status": "error", "error": f"{type(exc).__name__}: {exc}"}
        write_json(OUT / "audit" / "device_probes.json", probes)
    write_json(OUT / "audit" / "summary.json", {
        "baseline_parameter_roundoff": roundoff, "baseline_parameters": baseline,
        "fresh_failed_corner_ids": failed,
        "frozen_failed_corner_ids": frozen_failed,
        "full_exact_robust_violation": result["robust_feedback"]["exact_robust_violation"],
        "ledger": ledger.summary(),
    })
    archive_activity("baseline_and_device_audit", OUT / "baseline",
                     command="C:/Anaconda/python.exe scripts/task9_6_run_phase_b.py audit")
    archive_activity("device_audit_probes", OUT / "audit",
                     command="C:/Anaconda/python.exe scripts/task9_6_run_phase_b.py audit")
    print(f"Audit complete: {failed}, {ledger.summary()['process_count']} total processes", flush=True)


def _diagnostic_score(result: dict) -> tuple:
    """Only five-corner descriptive ranking, never the exact robust score."""
    components = {name: [] for name in CONSTRAINT_NAMES}
    passed_stages = 0
    margin = 0.0
    for row in result["corners"]:
        op = row["v2_op"]
        if not op["analysis_errors"].get("op"):
            for name, value in op["constraint_components"].items():
                components[name].append(value)
            passed_stages += int(all(value == 0 for value in op["constraint_components"].values()))
        probe = row["diagnostic_op"]
        if probe.get("process_status") == "success":
            margin += sum(max(0, -device["model_internal_on_margin_v"])
                          + max(0, -device["model_internal_vdsat_headroom_v"])
                          for device in probe["devices"].values())
    lower = sum(max(values) for values in components.values() if values)
    return (-passed_stages, lower, margin, parameter_hash(result["parameters"]))


def phase_sensitivity(ledger: BudgetLedger, executable: str) -> None:
    if not (OUT / "audit/summary.json").is_file():
        raise RuntimeError("fresh device audit must finish before sensitivity")
    proposals = read_json(PROPOSALS)
    corners = read_json(NEAR)["selected_corner_ids"]
    if proposals["candidate_count"] != 48 or len(corners) != 5:
        raise ValueError("frozen sensitivity inventory mismatch")
    rows = []
    for index, item in enumerate(proposals["candidates"]):
        name = f"sensitivity/candidate_{index:02d}"
        path = OUT / name / "diagnostic.json"
        if path.exists():
            result = read_json(path)
        else:
            ledger.require_capacity(ACTIVITY["sensitivity"], processes=20)
            before = ledger.process_count
            result = evaluate_task9_6_v2_local_diagnostic(
                parameters=item["parameters"], corner_ids=corners,
                evaluation_directory=OUT / name / "raw", executable=executable,
                ledger=ledger, activity=ACTIVITY["sensitivity"],
                candidate_id=f"sensitivity_{index:02d}")
            actual = ledger.process_count - before
            if actual != 20:
                raise RuntimeError(f"sensitivity candidate {index} used {actual}, expected 20; stop for audit")
            write_json(path, result)
        rows.append({"index": index, "parameter": item["parameter"],
                     "offset": item["normalized_offset"],
                     "parameters": item["parameters"],
                     "diagnostic_order": _diagnostic_score(result)})
        if index % 8 == 7:
            print(f"Sensitivity {index + 1}/48; ledger {ledger.process_count}", flush=True)
    write_json(OUT / "sensitivity/summary.json", {"rows": rows,
               "best_diagnostic_index": min(rows, key=lambda row: row["diagnostic_order"])["index"],
               "ledger": ledger.summary()})
    archive_activity("sensitivity", OUT / "sensitivity",
                     command="C:/Anaconda/python.exe scripts/task9_6_run_phase_b.py sensitivity")


def _de_scalar(feedback: dict) -> float | None:
    score = feedback.get("partial_search_score") or {}
    if not score.get("eligible"):
        return None
    import math
    lower = float(feedback["measured_robust_violation_lower_bound"])
    penalty = float(score["device_margin_penalty"])
    return (-10000.0 * feedback["passed_measured_stages"]
            - 100.0 * feedback["passed_complete_corners"]
            + (2 / math.pi) * math.atan(lower)
            + 0.01 * (2 / math.pi) * math.atan(penalty))


def _attention_subset() -> tuple[str, ...]:
    summary = read_json(OUT / "sensitivity/summary.json")
    baseline = read_json(OUT / "audit/summary.json")["baseline_parameters"]
    by_name = {}
    for row in summary["rows"]:
        improvement = -row["diagnostic_order"][0]
        by_name[row["parameter"]] = max(by_name.get(row["parameter"], -1), improvement)
    # Frozen rule: four largest measured five-corner pass-progress values,
    # ties resolved by variable name. Bounds remain the original 12-D bounds.
    return tuple(name for name, _ in sorted(by_name.items(),
                 key=lambda pair: (-pair[1], pair[0]))[:4])


def _local_proposals() -> list[dict]:
    frozen = load_experiment_config(FROZEN_TASK7_CONFIG)
    summary = read_json(OUT / "sensitivity/summary.json")
    anchor_index = summary["best_diagnostic_index"]
    anchor = read_json(PROPOSALS)["candidates"][anchor_index]["parameters"]
    focus = _attention_subset()
    rng = random.Random(96002)
    by_name = {item.name: item for item in frozen.search_space}
    proposals, seen = [], {parameter_hash(anchor)}
    while len(proposals) < 32:
        candidate = dict(anchor)
        for name in rng.sample(list(focus), k=2):
            item = by_name[name]
            position = normalized_position(item, float(candidate[name]))
            delta = rng.choice((-0.08, -0.04, -0.02, 0.02, 0.04, 0.08))
            candidate[name] = from_normalized(item, min(1.0, max(0.0, position + delta)))
        digest = parameter_hash(candidate)
        if digest in seen:
            continue
        seen.add(digest)
        proposals.append(candidate)
    return proposals


def _promote(batch: list[dict], promoted: set[str], batch_index: int,
             ledger: BudgetLedger, executable: str) -> dict | None:
    eligible = [row for row in batch
                if row["feedback"]["partial_search_score"]
                and row["feedback"]["partial_search_score"]["eligible"]
                and row["parameter_sha256"] not in promoted]
    if not eligible:
        return None
    selected = min(eligible, key=lambda row:
                   row["feedback"]["partial_search_score"]["ordering_key"])
    promoted.add(selected["parameter_sha256"])
    name = f"promotions/batch_{batch_index:02d}"
    full = evaluate_full_or_hierarchy(selected["parameters"], mode="full",
            activity=ACTIVITY["promotion"], name=name, ledger=ledger,
            executable=executable)
    archive_activity(f"promotion_batch_{batch_index:02d}", OUT / name,
                     command="C:/Anaconda/python.exe scripts/task9_6_run_phase_b.py search")
    return {"selected_candidate_id": selected["candidate_id"],
            "parameter_sha256": selected["parameter_sha256"],
            "full_path": str((OUT / name / "evaluation.json").relative_to(ROOT)).replace("\\", "/"),
            "exact_robust_violation": full["robust_feedback"]["exact_robust_violation"],
            "is_feasible": full["raw_v2_result"]["is_feasible"]}


def _positive_validation(parameters: dict, ledger: BudgetLedger, executable: str) -> dict:
    full = evaluate_full_or_hierarchy(parameters, mode="full",
        activity=ACTIVITY["confirmation"], name="witness/fresh_full",
        ledger=ledger, executable=executable)
    if full["raw_v2_result"]["is_feasible"] is not True:
        return {"fresh_full_positive": False}
    hierarchy = evaluate_full_or_hierarchy(parameters, mode="hierarchical",
        activity=ACTIVITY["positive_hierarchy"], name="witness/positive_hierarchy",
        ledger=ledger, executable=executable)
    if hierarchy["raw_v2_result"]["is_feasible"] is not True:
        return {"fresh_full_positive": True, "hierarchical_positive": False}
    frozen = load_experiment_config(FROZEN_TASK7_CONFIG)
    by_name = {item.name: item for item in frozen.search_space}
    neighbors = []
    for name in ("input_pair_length_m", "first_stage_load_width_m", "second_load_bias_v"):
        item = by_name[name]
        position = normalized_position(item, parameters[name])
        offsets = ((0.01, 0.02) if position <= 0.02 else
                   (-0.01, -0.02) if position >= 0.98 else (-0.01, 0.01))
        for offset in offsets:
            candidate = dict(parameters)
            candidate[name] = from_normalized(item, position + offset)
            neighbors.append(candidate)
    audit = []
    for index, candidate in enumerate(neighbors):
        full_neighbor = evaluate_full_or_hierarchy(candidate, mode="full",
            activity=ACTIVITY["neighborhood"], name=f"neighborhood/n{index}_full",
            ledger=ledger, executable=executable)
        hierarchical_neighbor = evaluate_full_or_hierarchy(candidate, mode="hierarchical",
            activity=ACTIVITY["neighborhood"], name=f"neighborhood/n{index}_hierarchical",
            ledger=ledger, executable=executable)
        audit.append({"index": index, "parameters": candidate,
                      "full_feasible": full_neighbor["raw_v2_result"]["is_feasible"],
                      "hierarchical_feasible": hierarchical_neighbor["raw_v2_result"]["is_feasible"],
                      "full_exact_robust_violation": full_neighbor["robust_feedback"]["exact_robust_violation"]})
        write_json(OUT / "neighborhood/audit.json", audit)
    archive_activity("positive_witness", OUT / "witness",
                     command="C:/Anaconda/python.exe scripts/task9_6_run_phase_b.py search")
    archive_activity("neighborhood", OUT / "neighborhood",
                     command="C:/Anaconda/python.exe scripts/task9_6_run_phase_b.py search")
    return {"fresh_full_positive": True, "hierarchical_positive": True,
            "neighborhood_complete": True,
            "neighborhood_consistent": all(row["full_feasible"] == row["hierarchical_feasible"]
                                           for row in audit)}


def phase_search(ledger: BudgetLedger, executable: str) -> None:
    if not (OUT / "sensitivity/summary.json").is_file():
        raise RuntimeError("frozen sensitivity study must complete before search")
    frozen = load_experiment_config(FROZEN_TASK7_CONFIG)
    de_config = replace(frozen, method="de", seed=96001, simulation_budget=64,
                        optimizer_config={"population_size": 8, "mutation": 0.8,
                                          "recombination": 0.7, "strategy": "best1bin"})
    optimizer = DifferentialEvolutionOptimizer(de_config, initialize_seeds(96001))
    local = _local_proposals()
    focus = _attention_subset()
    write_json(OUT / "search/prior_diagnosis.json", {"attention_subset": focus,
               "local_anchor_index": read_json(OUT / "sensitivity/summary.json")["best_diagnostic_index"],
               "seed_de": 96001, "seed_local": 96002,
               "de_internal_feedback": "bounded scalar encoding of frozen partial ordering; promotions use exact tuple"})
    batch, promoted, promotions, seen = [], set(), [], set()
    for index in range(96):
        is_de = index < 64
        parameters = optimizer.ask() if is_de else local[index - 64]
        parameters, _ = canonicalize_v2_parameters(parameters)
        digest = parameter_hash(parameters)
        if digest in seen:
            # Search proposals remain counted; duplicate cannot be promoted.
            print(f"Duplicate proposal {index}; retaining it as a charged search candidate", flush=True)
        seen.add(digest)
        name = f"search/candidate_{index:02d}"
        result = evaluate_full_or_hierarchy(parameters, mode="hierarchical",
            activity=ACTIVITY["search"], name=name, ledger=ledger,
            executable=executable)
        feedback = result["robust_feedback"]
        scalar = _de_scalar(feedback)
        if is_de:
            if scalar is None:
                optimizer.tell(parameters, {}, None, "failed")
            else:
                optimizer.tell(parameters, {"partial_proposal_score": scalar}, scalar, "success")
        row = {"candidate_id": index, "method": "de" if is_de else "local_trust_region",
               "parameter_sha256": digest, "parameters": parameters,
               "feedback": feedback, "simulation_status": "error" if scalar is None else "measured"}
        batch.append(row)
        write_json(OUT / "search" / "candidate_index.json", read_json(OUT / "search" / "candidate_index.json") + [row]
                   if (OUT / "search" / "candidate_index.json").exists() else [row])
        if len(batch) == 12:
            batch_number = (index + 1) // 12
            promoted_row = _promote(batch, promoted, batch_number, ledger, executable)
            if promoted_row is not None:
                promotions.append(promoted_row)
            write_json(OUT / "search/promotions.json", promotions)
            archive_activity(f"search_batch_{batch_number:02d}", OUT / "search",
                             command="C:/Anaconda/python.exe scripts/task9_6_run_phase_b.py search")
            print(f"Search {index + 1}/96, promotions {len(promotions)}, processes {ledger.process_count}", flush=True)
            if promoted_row and promoted_row["is_feasible"]:
                positive = _positive_validation(parameters=next(row["parameters"] for row in batch
                            if row["candidate_id"] == promoted_row["selected_candidate_id"]),
                            ledger=ledger, executable=executable)
                write_json(OUT / "witness/positive_validation.json", positive)
                print("Measured promoted 15/15 positive; stopped search for fresh validation", flush=True)
                return
            batch = []
    write_json(OUT / "search/summary.json", {"candidate_count": 96,
               "promotion_count": len(promotions), "promotions": promotions,
               "witness_found": False, "ledger": ledger.summary()})
    archive_activity("search_final", OUT / "search",
                     command="C:/Anaconda/python.exe scripts/task9_6_run_phase_b.py search")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("audit", "sensitivity", "search"))
    args = parser.parse_args()
    if not AUTH.is_file():
        raise RuntimeError("Phase B has no separate authorization record")
    executable = resolve_ngspice_executable("ngspice")
    if executable is None:
        raise RuntimeError("ngspice is unavailable; no Phase-B process started")
    ledger = BudgetLedger(OUT / "process_ledger.jsonl")
    if args.phase == "audit":
        phase_audit(ledger, executable)
    elif args.phase == "sensitivity":
        phase_sensitivity(ledger, executable)
    else:
        phase_search(ledger, executable)
    write_json(OUT / "ledger_summary.json", ledger.summary())


if __name__ == "__main__":
    main()
