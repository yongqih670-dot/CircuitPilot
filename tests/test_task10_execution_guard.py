"""Task 10 release must remain machine-blocked without real evidence."""

import json

import pytest

from circuitpilot.task10_execution_guard import (
    DEFAULT_GATE, check_task10_execution_guard, require_task10_execution_guard,
)
from circuitpilot.task9_protocol import PVT_BENCHMARK_HASH


def test_initial_machine_gate_denies_task10():
    decision = check_task10_execution_guard()
    assert not decision.allowed
    assert any("verified_real_pvt_witness" in reason for reason in decision.reasons)
    with pytest.raises(RuntimeError, match="Task 10 formal execution blocked"):
        require_task10_execution_guard()


def test_boolean_only_release_cannot_unlock_without_hashed_evidence(tmp_path):
    gate = json.loads(DEFAULT_GATE.read_text(encoding="utf-8"))
    for name in ("verified_real_pvt_witness", "positive_screening_validation",
                 "neighborhood_consistency_audit_complete", "witness_matrix_complete",
                 "corner_application_checks_pass"):
        gate[name] = True
    gate.update(corner_count=15, analysis_count=45, analysis_errors=0)
    path = tmp_path / "forged.json"
    path.write_text(json.dumps(gate), encoding="utf-8")
    decision = check_task10_execution_guard(path)
    assert not decision.allowed
    assert "release evidence" in decision.reasons[0]


def test_old_task9_hash_cannot_be_selected(tmp_path):
    gate = json.loads(DEFAULT_GATE.read_text(encoding="utf-8"))
    gate["selected_benchmark_hash"] = PVT_BENCHMARK_HASH
    path = tmp_path / "old.json"
    path.write_text(json.dumps(gate), encoding="utf-8")
    decision = check_task10_execution_guard(path)
    assert not decision.allowed
    assert any("old, unapproved" in reason for reason in decision.reasons)
