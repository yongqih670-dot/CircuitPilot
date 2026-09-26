"""Offline Task 9.6 evidence closure; intentionally never runs ngspice."""

from __future__ import annotations

import csv
import gzip
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from circuitpilot.environment_fingerprint import collect_environment_fingerprint
from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.simulator import resolve_ngspice_executable
from circuitpilot.task9_protocol import CANONICAL_CORNER_ORDER, CONSTRAINT_NAMES
from circuitpilot.task9_6_sensitivity import normalized_position
from circuitpilot.task9_6_v2_evaluator import APPROVED_BENCHMARK_V2_HASH, FROZEN_TASK7_CONFIG


OUT = ROOT / "research_runs/task9_6_phase_b"
DEST = ROOT / "research/sky130/two_stage_ota/task9_6"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def dump(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True,
                               allow_nan=False) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def deterministic_gzip(source: Path, destination: Path) -> dict:
    with source.open("rb") as input_handle, destination.open("wb") as output_handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=output_handle,
                           compresslevel=9, mtime=0) as compressed:
            for chunk in iter(lambda: input_handle.read(1024 * 1024), b""):
                compressed.write(chunk)
    return {"source_path": str(source.relative_to(ROOT)).replace("\\", "/"),
            "source_bytes": source.stat().st_size, "source_sha256": digest(source),
            "gzip_path": str(destination.relative_to(ROOT)).replace("\\", "/"),
            "gzip_bytes": destination.stat().st_size, "gzip_sha256": digest(destination)}


def full_inventory() -> list[dict]:
    paths = [("baseline", OUT / "baseline/evaluation.json")]
    paths.extend((f"promotion_{i:02d}", OUT / "promotions" / f"batch_{i:02d}" / "evaluation.json")
                 for i in range(1, 9))
    rows = []
    for origin, path in paths:
        wrapper = load(path)
        feedback, raw = wrapper["robust_feedback"], wrapper["raw_v2_result"]
        if (wrapper["benchmark_v2_hash"] != APPROVED_BENCHMARK_V2_HASH
                or raw["mode"] != "full" or raw["process_calls"] != 45
                or feedback["robust_evaluation_status"] != "exact"
                or feedback["measured_analysis_count"] != 45
                or feedback["exact_robust_violation"] is None
                or any(any(value is not None for value in corner["analysis_errors"].values())
                       for corner in raw["corners"])):
            raise RuntimeError(f"invalid Full matrix: {path}")
        parameters = raw["parameters"]
        parameter_digest = sha256(json.dumps(parameters, sort_keys=True,
                                             separators=(",", ":")).encode()).hexdigest()
        failures = [corner["corner_id"] for corner in raw["corners"]
                    if any(value > 0 for value in corner["constraint_components"].values())]
        performance_failures = sorted({name for corner in raw["corners"]
             for name, value in corner["constraint_components"].items()
             if name != "operating_region" and value > 0})
        rows.append({
            "origin": origin, "matrix_path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "matrix_sha256": digest(path), "parameters": parameters,
            "parameter_sha256": parameter_digest,
            "exact_robust_violation": feedback["exact_robust_violation"],
            "passed_corners": feedback["passed_complete_corners"],
            "is_feasible": raw["is_feasible"], "failed_corner_ids": failures,
            "performance_failed_components": performance_failures,
            "worst_power_w": max(corner["metrics"]["dc_power_w"] for corner in raw["corners"]),
        })
    if len({row["parameter_sha256"] for row in rows}) != 9:
        raise RuntimeError("Full ranking requires nine distinct parameter vectors")
    return sorted(rows, key=lambda row: (row["exact_robust_violation"],
                                         row["worst_power_w"], row["parameter_sha256"]))


def boundary_analysis(full: list[dict], search_space) -> tuple[list[dict], dict]:
    top = full[:8]
    rows = []
    counts = {item.name: {"lower_5pct": 0, "upper_5pct": 0} for item in search_space}
    for rank, candidate in enumerate(top, 1):
        for item in search_space:
            position = normalized_position(item, candidate["parameters"][item.name])
            lower, upper = position <= 0.05, position >= 0.95
            counts[item.name]["lower_5pct"] += int(lower)
            counts[item.name]["upper_5pct"] += int(upper)
            rows.append({"rank": rank, "origin": candidate["origin"],
                         "parameter_sha256": candidate["parameter_sha256"],
                         "exact_robust_violation": candidate["exact_robust_violation"],
                         "parameter": item.name, "coordinate": "log" if item.log else "linear",
                         "raw_value": candidate["parameters"][item.name],
                         "normalized_position": position,
                         "near_lower_5pct": lower, "near_upper_5pct": upper})
    with (DEST / "BOUNDARY_CONCENTRATION.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {"schema_version": "task9_6_boundary_concentration_v1",
               "top_unique_full_count": len(top), "ranked_by":
               ["exact_robust_violation", "worst_power_w", "parameter_sha256"],
               "near_bound_rule": "normalized position <=0.05 or >=0.95; log sampled parameters in log coordinate",
               "counts": counts}
    dump(DEST / "boundary_concentration.json", summary)
    return rows, summary


def validate_archives() -> list[dict]:
    references = []
    for path in sorted((DEST / "archives").glob("*.json")):
        manifest = load(path)
        archive = ROOT / manifest["archive_path"]
        tracked_archive = DEST / "raw_evidence" / archive.name
        if (not archive.is_file() or archive.stat().st_size != manifest["bytes"]
                or digest(archive) != manifest["sha256"]
                or not tracked_archive.is_file()
                or tracked_archive.stat().st_size != manifest["bytes"]
                or digest(tracked_archive) != manifest["sha256"]):
            raise RuntimeError(f"evidence archive hash/size mismatch: {path.name}")
        with ZipFile(tracked_archive) as zipfile:
            if zipfile.testzip() is not None or len(zipfile.namelist()) != manifest["source_files"]:
                raise RuntimeError(f"evidence archive CRC/inventory mismatch: {path.name}")
        references.append({"activity": path.stem, **manifest,
                           "git_archive_path": str(tracked_archive.relative_to(ROOT)).replace("\\", "/")})
    if len(references) != 21:
        raise RuntimeError(f"expected 21 immutable audit/sensitivity/search/promotions archives, got {len(references)}")
    lines = ["# Task 9.6 Phase-B raw evidence archives", "",
             "All 21 ZIP archives were checked for path, size, SHA-256, file",
             "count and complete ZIP CRC. Byte-identical copies are Git-tracked",
             "under `raw_evidence/`; the original activity-time archives remain",
             "under ignored `research_runs/task9_6_phase_b/archives/`. Git-tracked",
             "copies make the raw ngspice netlists, waveforms/OP vectors and logs",
             "available in a checkout. Independent backup is still advisable.", "",
             "| Activity | ZIP bytes | SHA-256 | Files | Source commit | Git archive |",
             "| --- | ---: | --- | ---: | --- | --- |"]
    for ref in references:
        lines.append(f"| `{ref['activity']}` | {ref['bytes']:,} | `{ref['sha256']}` | "
                     f"{ref['source_files']:,} | `{ref['associated_commit']}` | "
                     f"`{ref['git_archive_path']}` |")
    lines.extend(["", "Every per-archive JSON in `archives/` also records the",
                  "original relative archive path and reproduction command.",
                  "The complete per-process ledger and all candidate summaries",
                  "are losslessly compressed and Git-tracked separately.", ""])
    (DEST / "EVIDENCE_ARCHIVE_MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")
    return references


def main() -> None:
    ledger = load(OUT / "ledger_summary.json")
    plan = load(DEST / "execution_plan.json")
    if (ledger["process_count"] != 1595 or
            ledger["accumulated_simulator_seconds"] > plan["global_limits"]["maximum_accumulated_simulator_seconds"] or
            ledger["process_count"] > plan["global_limits"]["maximum_ngspice_processes"] or
            ledger["orphaned_process_starts"]):
        raise RuntimeError("Phase-B ledger is inconsistent or over budget")
    events = [json.loads(line) for line in (OUT / "process_ledger.jsonl").read_text(encoding="utf-8").splitlines()]
    if (len(events) != 3190 or sum(event["type"] == "start" for event in events) != 1595
            or any(event.get("status") != "success" for event in events if event["type"] == "finish")):
        raise RuntimeError("Phase-B process ledger has missing/error events")
    search = load(OUT / "search/candidate_index.json")
    promotions = load(OUT / "search/promotions.json")
    if (len(search) != 96 or len(promotions) != 8 or
            sum(row["method"] == "de" for row in search) != 64 or
            sum(row["method"] == "local_trust_region" for row in search) != 32 or
            any(row["feedback"]["robust_evaluation_status"] != "partial" or
                row["feedback"]["exact_robust_violation"] is not None for row in search)):
        raise RuntimeError("search candidate/method/partial inventory mismatch")
    full = full_inventory()
    if any(row["is_feasible"] for row in full):
        raise RuntimeError("positive witness path requires separate release closure")
    best, best_partial = full[0], min(search,
        key=lambda row: row["feedback"]["partial_search_score"]["ordering_key"])
    if best["exact_robust_violation"] != 1.0 or best["passed_corners"] != 12:
        raise RuntimeError("unexpected best complete result; inspect before deciding")
    frozen = load_experiment_config(FROZEN_TASK7_CONFIG)
    rows, boundary = boundary_analysis(full, frozen.search_space)
    archives = validate_archives()
    evidence = {
        "schema_version": "task9_6_phase_b_result_v1",
        "benchmark_v2_hash": APPROVED_BENCHMARK_V2_HASH,
        "decision": "B", "verified_real_pvt_witness": False,
        "task10_unlocked": False, "benchmark_v3_implemented": False,
        "no_witness_within_preregistered_budget": True,
        "ledger": ledger,
        "search_candidate_count": 96, "de_candidate_count": 64,
        "local_candidate_count": 32, "full_promotion_count": 8,
        "complete_full_matrix_count": len(full),
        "fresh_witness_verification_count": 0,
        "positive_hierarchical_validation_count": 0,
        "neighborhood_validation_count": 0,
        "best_exact_candidate": best,
        "best_partial_candidate": {
            "candidate_id": best_partial["candidate_id"],
            "parameter_sha256": best_partial["parameter_sha256"],
            "measured_analysis_count": best_partial["feedback"]["measured_analysis_count"],
            "unknown_analysis_count": len(best_partial["feedback"]["unknown_analyses"]),
            "measured_robust_violation_lower_bound": best_partial["feedback"]["measured_robust_violation_lower_bound"],
            "was_promoted_to_full": any(row["selected_candidate_id"] == best_partial["candidate_id"] for row in promotions),
        },
        "full_candidates_ranked": full,
        "boundary_top_count": boundary["top_unique_full_count"],
        "archive_count": len(archives),
    }
    dump(DEST / "phase_b_results.json", evidence)
    compressed = [
        deterministic_gzip(OUT / "process_ledger.jsonl", DEST / "process_ledger.jsonl.gz"),
        deterministic_gzip(OUT / "search/candidate_index.json", DEST / "search_candidate_index.json.gz"),
        deterministic_gzip(OUT / "promotions/batch_07/evaluation.json", DEST / "best_full_v2_matrix.json.gz"),
    ]
    dump(DEST / "compressed_evidence_manifest.json", {"files": compressed})
    executable = resolve_ngspice_executable("ngspice")
    fingerprint = collect_environment_fingerprint(executable or "ngspice")
    dump(DEST / "environment_fingerprint.json", fingerprint)
    model = frozen.circuit_config.model
    lines = ["# Decision after Research Task 9.6 — B", "",
             "**Decision B: no Benchmark-v2 witness found within the preregistered",
             "diagnostic budget, but measured device and performance evidence",
             "supports a separately reviewed Benchmark-v3 proposal.** This is",
             "not a proof that v2 is infeasible or that v3 is required.", "",
             "Nine unique complete Full-PVT matrices (fresh baseline plus eight",
             "method-blind promotions) were evaluated. None was 15/15 feasible.",
             "The best complete result had exact robust violation 1.0 and 12/15",
             "passing corners. It met every frozen performance hard specification",
             "in all 15 corners; only the v2 operating-region component failed",
             "in `ss__high_v_low_t`, `fs__nominal`, and `fs__high_v_low_t`.",
             "The separate baseline device probe found finite Id/gm in devices",
             "rejected by that same v2 on predicate; baseline additionally missed",
             "negative slew in one corner. These observations justify proposing",
             "a future measured-current/model-saturation semantics study, not",
             "silently altering v2 or declaring the candidate feasible.", "",
             "Task 10 stays blocked: no fresh positive 45-analysis verification,",
             "positive Hierarchical validation or neighborhood audit exists, and",
             "the machine-readable Task 10 guard remains false. Benchmark v3 is",
             "proposal-only and needs explicit user approval in a separate task.",
             "The exact budgeted conclusion is **no witness found within this",
             "preregistered diagnostic budget**.", ""]
    (DEST / "DECISION_AFTER_TASK9_6.md").write_text("\n".join(lines), encoding="utf-8")
    proposal = ["# Benchmark-v3 proposal — not adopted or implemented", "",
      "The corrected Benchmark v2 stays frozen under hash `" + APPROVED_BENCHMARK_V2_HASH + "`.",
      "The old Task 9 v1 semantics must not be reinstated. This document",
      "proposes only a separately approved research task.", "",
      "## Measured physical motivation", "",
      "The best Task 9.6 Full candidate satisfies gain, UGF, PM, power,",
      "output and both slew minima at all 15 frozen corners, while the binary",
      "v2 operating-region predicate alone rejects three corners. The fresh",
      "baseline of the same topology fails that predicate at the same three",
      "corners, and its rejected input/load devices carry roughly 1.6–3.0 µA",
      "internal model Id with meaningful gm, not zero current. Model VDSAT",
      "headroom, signed external coordinates, stage nodes and gm/abs(Id) are",
      "recorded in `DEVICE_ON_CONDITION_AUDIT.md`. Local perturbations show",
      "coupling among tail/input/load dimensions and the region margin.", "",
      "## Proposed separate v3 investigation", "",
      "Measure signed Id, gm, gm/abs(Id), model VTH/VDSAT and model saturation",
      "for the best complete candidate at **all 15 corners** using a new",
      "approved probe budget. Pre-register and physically calibrate a candidate",
      "on/operating-region predicate that distinguishes a conducting, useful",
      "amplifying device from a truly ineffective one. A possible hypothesis",
      "is a finite, independently justified Id/gm criterion combined with",
      "model VDSAT headroom, but no threshold or v3 hash is selected here.",
      "Run fresh calibration and evaluate the unchanged hard performance",
      "specifications, 15-corner set and technology legality before proposing",
      "a versioned v3. Alternative bias/sizing-space revisions may be studied",
      "only with separate PDK and physical justification; none is adopted.", "",
      "A finite failed v2 search alone is **not** evidence of global",
      "infeasibility. Nor do the baseline Id probes prove the best candidate",
      "would pass any proposed v3 semantics. No v3 implementation, formal",
      "recalibration or Task 10 execution is authorized by this proposal.", ""]
    (DEST / "BENCHMARK_V3_PROPOSAL.md").write_text("\n".join(proposal), encoding="utf-8")
    counts = ledger["activity_process_counts"]
    report = ["# Task 9.6 PVT feasibility diagnosis — final report", "",
      "**Decision B.** No real Benchmark-v2 15/15 PVT-feasible OTA was found",
      "within the frozen Phase-B plan. This is not proof of v2 infeasibility.",
      "Task 10 remains machine-blocked; v3 remains an unimplemented proposal.", "",
      "## Integrity, version and objective semantics", "",
      "Tasks 6–9.5 remain byte-identical under `history_freeze.json`.",
      "The Task 6 RMST wording addendum distinguishes genuine positive-tail",
      "extrapolation on the candidate-count axis from conservative common",
      "truncation at 92 AC calls; Full did have observations through 200 AC.",
      "Every corrected candidate-level Full/Hierarchical search evaluation",
      "called the explicit Task 9.5 `model_consistent_saturation_v2`",
      "evaluator under hash `" + APPROVED_BENCHMARK_V2_HASH + "`.",
      "The five-corner diagnostic path called that v2 evaluator for OP-only",
      "classification, then reused the unchanged physical AC/transient stage",
      "measurement functions; it never called the Task 9 v1 robust evaluator",
      "or used the old v1 hash as corrected semantics.",
      "Only fresh 15×(OP+AC+transient) Full matrices produce exact robust",
      "violation. The 96 Hierarchical search results retain unmeasured stages",
      "as UNKNOWN and use a separate partial proposal ordering; zero measured",
      "violation is not a feasibility claim.", "",
      "## Preregistered and actual budget", "",
      "The frozen plan capped 6,500 ngspice processes, 6,000 accumulated",
      "simulator seconds and ten wall-clock hours, with stricter per-activity",
      "allocations. Search was capped at 64 seeded DE + 32 seeded local",
      "proposals, eight method-blind Full promotions and six-neighbor",
      "validation only after a positive witness. The plan was not extended.", "",
      "| Activity | Actual ngspice processes |",
      "| --- | ---: |"]
    for name, count in counts.items():
        report.append(f"| `{name}` | {count} |")
    report.extend([f"| **Total** | **{ledger['process_count']}** |", "",
      f"Accumulated measured/charged simulator time: **{ledger['accumulated_simulator_seconds']:.3f} s**.",
      "All 1,595 starts have finishes and every ngspice process returned success;",
      "no retry or analysis-error process was charged. The search stopped when",
      "both the 96-candidate and eight-promotion caps were reached, not because",
      "the larger global process/time ceilings were exhausted. No extra run",
      "was made to consume unused allowance.", "",
      "## Device-on, bias and coordinate diagnosis", "",
      "`DEVICE_ON_CONDITION_AUDIT.md` records all seven devices in each of",
      "the three failed baseline corners: signed external VGS/VDS, NFET",
      "VGS/VDS or PFET VSG/VSD, internal model VTH/VDSAT, margins, signed Id,",
      "gm, gds, floor-gated gm/abs(Id), supply current, stage nodes, functional",
      "metrics, and independent on/saturation/function flags. The current",
      "floor is |Id|>1e-12 A; smaller or missing currents make gm/Id invalid,",
      "never artificially huge. Two baseline failed corners missed only the",
      "v2 on predicate; the FS high-VDD/cold corner also missed negative slew.",
      "Meaningful measured current/gm in predicate-failing devices does not",
      "turn a hard v2 failure into a pass. It argues for a separately calibrated",
      "semantics proposal. One design cannot establish a unique cause across",
      "the full feasible region.", "",
      "## Local sensitivity and physical search attention", "",
      "The 48 frozen, distinct, in-bounds proposals were measured at the five",
      "preselected near-constraint corners. Each used 15 standard stage",
      "analyses plus five signed-current diagnostic OP probes. All 240",
      "candidate-corner groups succeeded. Linear/log normalized coordinates",
      "and one-sided boundary perturbations avoided out-of-bounds duplicates.",
      "`LOCAL_ROBUST_SENSITIVITY.csv` contains 1,680 role-corner records",
      "with signed differences for device and performance metrics; the local",
      "report documents the ordering and limitations. Search attention used",
      ", ".join(f"`{name}`" for name in load(DEST / "sensitivity_analysis.json")["diagnostic_attention_subset"])
      + "; the original 12-D Benchmark-v2 bounds remained unchanged.",
      "The two nonfailing preselected baseline Id probes were completed after",
      "the candidate batch rather than before it; this order deviation is",
      "disclosed and charged, without post hoc corner selection.", "",
      "## Search, exact ranking and boundary concentration", "",
      "The existing sequential DE implementation used seed 96001 for 64",
      "proposals; deterministic local refinement used seed 96002 for 32.",
      "The same frozen partial score promoted one eligible unique candidate",
      "after each batch of 12. The 96 partial results consumed 225 analyses;",
      "85 stopped after the first measured stage. They were never ranked as",
      "exact. Eight promoted candidates each received a fresh Full matrix",
      "(360 further analyses). With the fresh baseline, nine unique Full",
      "matrices form the exact ranking.", "",
      "| Exact rank | Origin | Violation | Passed corners | Failed corners |",
      "| ---: | --- | ---: | ---: | --- |"])
    for rank, row in enumerate(full, 1):
        report.append(f"| {rank} | `{row['origin']}` | {row['exact_robust_violation']:.9g} | "
                      f"{row['passed_corners']}/15 | {', '.join(row['failed_corner_ids'])} |")
    report.extend(["", f"The best partial proposal was candidate {best_partial['candidate_id']}",
      f"with {best_partial['feedback']['measured_analysis_count']}/45 measured stages",
      f"and {len(best_partial['feedback']['unknown_analyses'])} UNKNOWN stages.",
      "It was promoted; its independent Full result is the best exact negative",
      "matrix (violation 1.0, 12/15). The best complete design has all hard",
      "**performance** components zero in all 15 corners, but its operating-",
      "region component is one in three corners. Therefore it is not a v2",
      "witness. Top eight unique Full matrices, ranked before inspection by",
      "exact violation, worst power and parameter hash, have 96 parameter",
      "position rows in `BOUNDARY_CONCENTRATION.csv`. Log-sampled variables",
      "use log normalized coordinates; near-bound counts use fixed 5% bands.",
      "Among those eight, compensation capacitance is in the upper 5% for",
      "five candidates and input-pair length for four; the capacitor uses",
      "its **log-space** position. The full per-variable lower/upper counts",
      "are in `boundary_concentration.json`. These adaptive-sample counts",
      "are descriptive, not causal evidence.", "",
      "## Witness, positive screening and neighborhood status", "",
      "No promoted Full candidate passed 15/15. Thus no separate fresh",
      "45-analysis positive witness verification, positive Hierarchical",
      "validation, six-neighbor consistency audit or `PVT_FEASIBILITY_WITNESS.md`",
      "was created. This follows the conditional frozen plan and leaves the",
      "machine-readable Task 10 guard false. No fabricated positive tests",
      "or neighborhood categories are reported.", "",
      "## Provenance, proposal and limitations", "",
      f"PDK commit: `{model.pdk_commit}`; model SHA-256:",
      f"`{model.model_sha256()}`; library SHA-256:",
      f"`{model.library_sha256()}`. The exact software/OS/ngspice fingerprint",
      "is in `environment_fingerprint.json`. The 21 raw ZIPs passed",
      "hash/size/inventory/CRC verification; individual source commits and",
      "reproduction commands are listed in `EVIDENCE_ARCHIVE_MANIFEST.md`.",
      "The Git-tracked compressed process ledger, candidate index and best",
      "Full matrix are bound by `compressed_evidence_manifest.json`.",
      "Byte-identical ZIP copies are Git-tracked under `raw_evidence/`, so a",
      "checkout contains the raw netlists, ngspice logs and OP/waveform data.",
      "Independent archival backup remains advisable.", "",
      "`BENCHMARK_V3_PROPOSAL.md` proposes a separately approved physical",
      "on/region-semantics calibration study, supported by nonzero Id/gm",
      "and complete performance passes, but implements nothing. The best",
      "candidate's signed Id was not independently probed; the baseline",
      "Id evidence must not be transferred to it as if measured. The finite",
      "adaptive search cannot establish global v2 infeasibility or universal",
      "causality. Decision B therefore keeps Task 10 blocked and asks for",
      "separate review of any versioned v3 proposal, without weakening hard",
      "performance specs or PVT corner count.", ""])
    (DEST / "TASK9_6_FEASIBILITY_DIAGNOSIS_REPORT.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Task 9.6 offline closure: Decision B, {len(full)} Full matrices, {len(archives)} archives")


if __name__ == "__main__":
    main()
