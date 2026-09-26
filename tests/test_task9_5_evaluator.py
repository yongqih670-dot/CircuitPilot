"""Task 9.5 independent v2 verifier and positive-path regression tests."""

from pathlib import Path

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments.task9_evaluator import StageMeasurement
from circuitpilot.sky130_two_stage_ota import DEVICE_ROLES
from circuitpilot.task9_protocol import CANONICAL_CORNER_ORDER, CORNER_BY_ID, STATIC_WORST_FIRST_ORDER
from circuitpilot import task9_5_evaluator


ROOT = Path(__file__).resolve().parents[1]
TASK7 = ROOT / "research" / "sky130" / "two_stage_ota" / "task7_frozen.yaml"


def _fake_stage(kind, *, corner_id, bad_corner=None, **_kwargs):
    corner = CORNER_BY_ID[corner_id]
    devices = {
        role: {"vgs": 0.9, "vds": 0.5, "vth": 0.4, "vdsat": 0.2,
               "gm": 1e-4, "gds": 1e-6}
        for role in DEVICE_ROLES
    }
    if corner_id == bad_corner and kind == "op":
        devices[next(iter(DEVICE_ROLES))]["vds"] = 0.1
    if kind == "op":
        metrics = {"dc_power_w": 1e-4, "output_dc_voltage": 0.9}
        statuses = {}
        evidence = {"device_quantities": devices,
                    "measured_supply_voltage_v": corner.vdd_v}
    elif kind == "ac":
        metrics = {"dc_gain_db": 20.0, "ugf_hz": 1e6,
                   "phase_margin_deg": 60.0}
        statuses = {"ugf_status": "measured", "phase_margin_status": "measured"}
        evidence = {}
    else:
        metrics = {"positive_slew_v_per_s": 1e6,
                   "negative_slew_v_per_s": 1e6}
        statuses = {"positive_slew_status": "measured",
                    "negative_slew_status": "measured"}
        evidence = {}
    return StageMeasurement(kind, metrics, statuses, evidence, None, 0.1, 0.1,
                            False, corner.temperature_c)


def _run(tmp_path, mode):
    return task9_5_evaluator.evaluate_v2_candidate(
        base_config=load_experiment_config(TASK7).circuit_config,
        parameters={}, evaluation_directory=tmp_path / mode,
        executable="unused", timeout_seconds=60,
        start_frequency_hz=10, stop_frequency_hz=1e10,
        points_per_decade=30, mode=mode,
    )


def test_full_pvt_witness_requires_all_45_fresh_analyses(monkeypatch, tmp_path):
    calls = []

    def stage(kind, **kwargs):
        calls.append((kwargs["corner_id"], kind))
        return _fake_stage(kind, **kwargs)

    monkeypatch.setattr(task9_5_evaluator, "execute_real_pvt_stage", stage)
    result = _run(tmp_path, "full")
    assert result["is_feasible"] and result["complete_full_matrix"]
    assert result["process_calls"] == 45
    assert calls == [(corner, kind) for corner in CANONICAL_CORNER_ORDER
                     for kind in ("op", "ac", "transient")]
    assert all(all(row["application_checks"].values()) for row in result["corners"])


def test_positive_witness_passes_hierarchy_without_false_rejection(monkeypatch, tmp_path):
    monkeypatch.setattr(task9_5_evaluator, "execute_real_pvt_stage", _fake_stage)
    full = _run(tmp_path, "full")
    hierarchical = _run(tmp_path, "hierarchical")
    assert full["is_feasible"] and hierarchical["is_feasible"]
    assert hierarchical["process_calls"] == 45
    assert not hierarchical["complete_full_matrix"]
    assert hierarchical["first_failure"] is None


def test_hierarchical_rejects_measured_failure_and_marks_unrun_null(monkeypatch, tmp_path):
    first = STATIC_WORST_FIRST_ORDER[0]

    def stage(kind, **kwargs):
        return _fake_stage(kind, bad_corner=first, **kwargs)

    monkeypatch.setattr(task9_5_evaluator, "execute_real_pvt_stage", stage)
    result = _run(tmp_path, "hierarchical")
    assert result["process_calls"] == 1
    assert result["first_failure"] == {"corner_id": first, "stage": "op",
                                       "constraint": "operating_region"}
    assert not result["is_feasible"]
    assert sum(row["metrics"] is None for row in result["corners"]) == 14
