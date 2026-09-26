"""Offline checks of committed Task 9.6 Phase-B negative evidence."""

import gzip
from hashlib import sha256
import json
from pathlib import Path

from circuitpilot.task10_execution_guard import check_task10_execution_guard
from circuitpilot.task9_6_feedback import summarize_v2_robust_feedback


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "research/sky130/two_stage_ota/task9_6"


def _json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_budget_and_negative_decision_are_self_consistent():
    result = _json(ARTIFACTS / "phase_b_results.json")
    plan = _json(ARTIFACTS / "execution_plan.json")
    counts = result["ledger"]["activity_process_counts"]
    assert result["decision"] == "B"
    assert result["verified_real_pvt_witness"] is False
    assert result["no_witness_within_preregistered_budget"] is True
    assert result["search_candidate_count"] == 96
    assert result["de_candidate_count"] == 64
    assert result["local_candidate_count"] == 32
    assert result["full_promotion_count"] == 8
    assert result["complete_full_matrix_count"] == 9
    assert counts["sensitivity_48_candidates"] == 960
    assert counts["fresh_baseline_full"] == 45
    assert counts["full_promotion_8_candidates"] == 360
    assert counts["hierarchical_search_96_candidates"] == 225
    assert counts["device_audit_probes"] == 5
    assert sum(counts.values()) == result["ledger"]["process_count"] == 1595
    assert 1595 <= plan["global_limits"]["maximum_ngspice_processes"]
    assert result["ledger"]["accumulated_simulator_seconds"] < plan["global_limits"]["maximum_accumulated_simulator_seconds"]
    assert result["archive_count"] == 21
    assert not check_task10_execution_guard().allowed


def test_compressed_full_and_partial_evidence_recomputes_truthfully():
    manifest = _json(ARTIFACTS / "compressed_evidence_manifest.json")
    for entry in manifest["files"]:
        compressed = ROOT / entry["gzip_path"]
        assert sha256(compressed.read_bytes()).hexdigest() == entry["gzip_sha256"]
        assert sha256(gzip.decompress(compressed.read_bytes())).hexdigest() == entry["source_sha256"]
    with gzip.open(ARTIFACTS / "best_full_v2_matrix.json.gz", "rt", encoding="utf-8") as handle:
        wrapper = json.load(handle)
    feedback = summarize_v2_robust_feedback(wrapper["raw_v2_result"])
    assert wrapper["robust_feedback"] == feedback
    assert feedback["robust_evaluation_status"] == "exact"
    assert feedback["exact_robust_violation"] == 1.0
    assert feedback["passed_complete_corners"] == 12
    assert wrapper["raw_v2_result"]["is_feasible"] is False
    for corner in wrapper["raw_v2_result"]["corners"]:
        assert all(value == 0 for name, value in corner["constraint_components"].items()
                   if name != "operating_region")
    with gzip.open(ARTIFACTS / "search_candidate_index.json.gz", "rt", encoding="utf-8") as handle:
        search = json.load(handle)
    assert len(search) == 96
    assert all(row["feedback"]["robust_evaluation_status"] == "partial"
               and row["feedback"]["exact_robust_violation"] is None for row in search)
    assert {row["candidate_id"] for row in search} == set(range(96))


def test_all_raw_archives_are_git_mirrored_with_locked_content():
    manifests = sorted((ARTIFACTS / "archives").glob("*.json"))
    archives = sorted((ARTIFACTS / "raw_evidence").glob("*.zip"))
    assert len(manifests) == len(archives) == 21
    for path in manifests:
        manifest = _json(path)
        mirrored = ARTIFACTS / "raw_evidence" / Path(manifest["archive_path"]).name
        assert mirrored.stat().st_size == manifest["bytes"]
        assert sha256(mirrored.read_bytes()).hexdigest() == manifest["sha256"]
