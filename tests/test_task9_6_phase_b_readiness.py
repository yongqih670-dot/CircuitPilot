"""No-SPICE readiness tests required before Phase-B execution."""

from contextlib import nullcontext
import json
from types import SimpleNamespace

import pytest

from circuitpilot.experiments.task9_evaluator import StageMeasurement
from circuitpilot.task9_protocol import CANONICAL_CORNER_ORDER
from circuitpilot.task9_6_budget import BudgetExhausted, BudgetLedger
from circuitpilot import task9_6_local_diagnostic as local


ACTIVITY = "device_audit_probes"


def test_budget_ledger_fsyncs_success_and_failure_and_counts_both(tmp_path):
    ledger = BudgetLedger(tmp_path / "processes.jsonl")

    def success(_netlist, **_kwargs):
        return SimpleNamespace(elapsed_seconds=0.01)

    ledger.run(ACTIVITY, "case1", tmp_path / "one.cir", runner=success)
    assert ledger.process_count == 1
    assert ledger.activity_counts[ACTIVITY] == 1

    def failure(_netlist, **_kwargs):
        raise RuntimeError("synthetic process failure")

    with pytest.raises(RuntimeError, match="synthetic"):
        ledger.run(ACTIVITY, "case2", tmp_path / "two.cir", runner=failure)
    recovered = BudgetLedger(tmp_path / "processes.jsonl")
    assert recovered.process_count == 2
    assert recovered.activity_counts[ACTIVITY] == 2
    assert len(recovered.finishes) == 2
    assert recovered.finishes[2]["elapsed_estimated"] is True
    assert recovered.simulator_seconds >= 0


def test_orphaned_start_consumes_reserved_timeout_and_activity_cap(tmp_path):
    ledger = BudgetLedger(tmp_path / "crash.jsonl")
    ledger._append({"type": "start", "sequence": 1, "activity": ACTIVITY,
                    "candidate_id": "interrupted", "timestamp_utc":
                    "2026-09-26T13:00:00+00:00", "netlist_path": "x.cir",
                    "reserved_timeout_seconds": 60.0})
    recovered = BudgetLedger(ledger.path)
    assert recovered.simulator_seconds == 60.0
    assert recovered.summary()["orphaned_process_starts"] == [1]
    recovered.plan["activity_process_allocations"][ACTIVITY] = 1
    with pytest.raises(BudgetExhausted):
        recovered.require_capacity(ACTIVITY)


def test_budget_rejects_missing_or_modified_approval(tmp_path):
    approval = tmp_path / "approval.json"
    approval.write_text(json.dumps({"schema_version": "task9_6_phase_b_authorization_v1",
                                    "approved": False}), encoding="utf-8")
    with pytest.raises(ValueError, match="authorization"):
        BudgetLedger(tmp_path / "ledger.jsonl", authorization_path=approval)


def test_diagnostic_op_netlist_preserves_original_vectors():
    config = SimpleNamespace(nfet_device_name="nfet", pfet_device_name="pfet")
    text = local.diagnostic_op_netlist("wrdata original v(out)\nquit\n.endc\n",
                                       "diag.dat", config)
    assert "wrdata original v(out)" in text
    assert "v(mirror) i(VDD)" in text
    assert "@m.xm1.mnfet[id]" in text
    assert "@m.xm3.mpfet[id]" in text
    assert text.count("[id]") == 7


def test_five_corner_runner_is_v2_partial_and_uses_ten_physical_stages(monkeypatch, tmp_path):
    corners = CANONICAL_CORNER_ORDER[:5]
    calls = []

    def fake_v2(**kwargs):
        assert kwargs["mode"] == "op_only"
        assert tuple(kwargs["corners"]) == corners
        return {"benchmark_v2_hash": "v2-test", "robust_feedback":
                {"exact_robust_violation": None},
                "raw_v2_result": {"corners": [{"corner_id": corner_id}
                                              for corner_id in CANONICAL_CORNER_ORDER]}}

    def fake_stage(kind, **kwargs):
        calls.append((kind, kwargs["corner_id"]))
        return StageMeasurement(kind, {"measured": 1.0}, {}, {}, None,
                                0.01, 0.02, False, 27.0)

    class FakeLedger:
        def meter(self, activity, candidate_id):
            assert activity == ACTIVITY and candidate_id == "local0"
            return nullcontext()

    monkeypatch.setattr(local, "evaluate_task9_6_benchmark_v2_candidate", fake_v2)
    monkeypatch.setattr(local, "execute_real_pvt_stage", fake_stage)
    monkeypatch.setattr(local, "run_diagnostic_op", lambda **kwargs: {"process_status": "success"})
    outcome = local.evaluate_task9_6_v2_local_diagnostic(
        parameters={}, corner_ids=corners, evaluation_directory=tmp_path,
        executable="unused", ledger=FakeLedger(), activity=ACTIVITY,
        candidate_id="local0")
    assert outcome["robust_evaluation_status"] == "partial"
    assert outcome["exact_robust_violation"] is None
    assert len(outcome["corners"]) == 5
    assert len(calls) == 10
    assert set(kind for kind, _ in calls) == {"ac", "transient"}
