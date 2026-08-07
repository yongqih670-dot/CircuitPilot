from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from circuitpilot.bandwidth import BandwidthStatus, measure_bandwidth
from circuitpilot.exceptions import ConfigError
from circuitpilot.experiments.analyzer import Sky130CommonSourceAnalyzer
from circuitpilot.experiments.config import (
    ConstraintDefinition,
    ConstraintOperator,
    NgspiceConfig,
    experiment_config_from_mapping,
    load_experiment_config,
)
from circuitpilot.experiments.objectives import ObjectiveEvaluator
from circuitpilot.experiments.recorder import EvaluationRecord
from circuitpilot.experiments.simulation import Sky130CommonSourceNgspiceSimulator
from circuitpilot.experiments.survival import kaplan_meier
from circuitpilot.sky130_common_source import generate_sky130_common_source_netlist
from circuitpilot.sky130_model import SKY130_DEVICE_NAME


TASK3_HASH = "d60664b436ce9a928da2db86ca83378d556f18ddcf54b633394609f67288bec9"
MODEL_HASH = "d88fa42b4f42f7b1f6987141aa92161865cfc9ff5fbdce9bbc9f137bde3a2f61"


def _task4_config():
    return load_experiment_config(
        Path("research/sky130/common_source/calibration_config.yaml")
    )


def test_sky130_model_provenance_and_content_hash() -> None:
    config = _task4_config()
    model = config.circuit_config.model
    metadata = model.metadata()
    assert metadata["device_name"] == SKY130_DEVICE_NAME
    assert metadata["pdk_release"] == "1.0.606"
    assert metadata["pdk_commit"] == "026824c7969ce6f4fc9678e6ca04b0a06a596c4b"
    assert metadata["primitive_commit"] == "403964dc7f9cca5ec1a8cc7b4f2a6f532b781676"
    assert metadata["model_sha256"] == MODEL_HASH
    assert metadata["model_file_count"] == 840


def test_missing_sky130_is_explicit_and_never_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SKY130_MODEL_LIBRARY", raising=False)
    monkeypatch.delenv("SKY130_PDK_ROOT", raising=False)
    with pytest.raises(ConfigError, match="fallback to the Task 3 N1 model is forbidden"):
        experiment_config_from_mapping(
            {
                "experiment": {
                    "name": "missing",
                    "circuit": "sky130_common_source",
                    "method": "random",
                    "seed": 0,
                    "simulation_budget": 1,
                },
                "search_space": {
                    "width_m": {"type": "float", "low": 0.42e-6, "high": 7e-6, "unit": "m", "technology_limits": {"low": 0.42e-6, "high": 7e-6}},
                    "length_m": {"type": "float", "low": 0.15e-6, "high": 1e-6, "unit": "m", "technology_limits": {"low": 0.15e-6, "high": 1e-6}},
                    "drain_resistance_ohm": {"type": "float", "low": 2e3, "high": 1e5, "unit": "ohm", "technology_limits": {"low": 1e2, "high": 1e6}},
                    "input_bias_v": {"type": "float", "low": 0.55, "high": 1.05, "unit": "V", "technology_limits": {"low": 0.0, "high": 1.8}},
                },
                "objectives": {"dc_power_w": {"type": "minimize"}},
                "circuit_config": {
                    "supply_voltage_v": 1.8,
                    "load_capacitance_f": 20e-15,
                    "temperature_c": 27.0,
                    "bandwidth_semantics_version": "post_peak_minus_3db_right_censoring_v1",
                    "censoring_policy": "fixed_window_right_censored_lower_bound_v1",
                    "difficulty_protocol_version": "task4_sky130_difficulty_v1",
                    "sky130_model": {},
                },
                "pvt_config": {},
            }
        )


def test_sky130_netlist_has_real_device_and_explicit_bulk() -> None:
    config = _task4_config()
    text = generate_sky130_common_source_netlist(
        config.circuit_config,
        {"width_m": 1.26e-6, "length_m": 0.15e-6, "drain_resistance_ohm": 1e4, "input_bias_v": 0.9},
        invariant_path="P:/invariant.spice",
        corner_path="P:/corner.spice",
        ac_output_path="R:/ac.dat",
        op_output_path="R:/op.dat",
        device_op_output_path="R:/device.dat",
        start_frequency_hz=10.0,
        stop_frequency_hz=1e10,
        points_per_decade=30,
    )
    assert "X1 out in 0 0 sky130_fd_pr__nfet_01v8 W=1.26 L=0.15" in text
    assert ".model N1" not in text and " N1 " not in text
    assert "i(vdd)" in text


def test_exact_bandwidth_measurement() -> None:
    result = measure_bandwidth((1.0, 10.0, 100.0), (10.0, 9.0, 5.0))
    assert result.bandwidth_status is BandwidthStatus.MEASURED
    assert result.bandwidth_hz == pytest.approx(31.6227766)
    assert result.bandwidth_lower_bound_hz is None


def test_right_censored_bandwidth_is_a_bound_not_a_value() -> None:
    result = measure_bandwidth((1.0, 10.0, 100.0), (10.0, 9.5, 9.0))
    assert result.bandwidth_status is BandwidthStatus.RIGHT_CENSORED
    assert result.bandwidth_hz is None
    assert result.bandwidth_lower_bound_hz == 100.0


def test_invalid_response_is_distinct_from_right_censoring() -> None:
    invalid = measure_bandwidth((1.0,), (10.0,))
    censored = measure_bandwidth((1.0, 10.0), (10.0, 9.0))
    assert invalid.bandwidth_status is BandwidthStatus.INVALID_RESPONSE
    assert censored.bandwidth_status is BandwidthStatus.RIGHT_CENSORED


def test_right_censored_record_is_not_a_simulation_failure() -> None:
    record = EvaluationRecord.now(
        experiment_id="e", run_id="r", circuit="sky130_common_source",
        method="random", seed=0, iteration=1, parameters={"x": 1.0},
        simulation_status="success", measurement_status="complete",
        bandwidth_status="right_censored", bandwidth_lower_bound_hz=1e10,
        failure_type=None, raw_metrics={"bandwidth_hz": None, "gain_db": 10.0},
        objective_value=0.1, constraint_violation=0.0, simulation_time=0.1,
        total_elapsed_time=0.1, run_directory="runs/evaluation_0001",
        ngspice_called=True,
    )
    assert record.simulation_status == "success"


def test_right_censored_lower_bound_can_satisfy_bandwidth_constraint() -> None:
    config = _task4_config()
    config = replace(
        config,
        constraints=(
            ConstraintDefinition("bandwidth_hz", ConstraintOperator.GREATER_EQUAL, 1e9),
        ),
    )
    result = ObjectiveEvaluator(config).evaluate(
        {"dc_power_w": 1e-4, "bandwidth_hz": None},
        bandwidth_status="right_censored",
        bandwidth_lower_bound_hz=1e10,
    )
    assert result.constraint_violation == 0.0
    assert result.is_feasible


def test_task4_hash_binds_model_and_censoring_semantics() -> None:
    config = _task4_config()
    assert config.circuit_config.model.model_sha256() == MODEL_HASH
    assert config.circuit_config.bandwidth_semantics_version in config.to_dict()["circuit_config"].values()
    assert len(config.computed_benchmark_hash()) == 64


def test_tampered_sky130_content_lock_is_rejected() -> None:
    config = _task4_config()
    with pytest.raises(ConfigError, match="model content hash mismatch"):
        replace(config.circuit_config.model, expected_model_sha256="0" * 64)


def test_fixed_measurement_window_changes_benchmark_hash() -> None:
    config = _task4_config()
    changed = replace(
        config,
        ngspice_config=NgspiceConfig(
            executable=config.ngspice_config.executable,
            start_frequency_hz=config.ngspice_config.start_frequency_hz,
            stop_frequency_hz=config.ngspice_config.stop_frequency_hz / 10.0,
            points_per_decade=config.ngspice_config.points_per_decade,
        ),
    )
    assert changed.computed_benchmark_hash() != config.computed_benchmark_hash()


def test_right_censored_lower_bound_below_threshold_is_infeasible() -> None:
    config = _task4_config()
    config = replace(
        config,
        constraints=(
            ConstraintDefinition("bandwidth_hz", ConstraintOperator.GREATER_EQUAL, 2e10),
        ),
    )
    result = ObjectiveEvaluator(config).evaluate(
        {"dc_power_w": 1e-4, "bandwidth_hz": None},
        bandwidth_status="right_censored",
        bandwidth_lower_bound_hz=1e10,
    )
    assert result.constraint_violation == pytest.approx(0.5)
    assert not result.is_feasible


def test_analysis_error_is_separate_from_ngspice_process_success() -> None:
    record = EvaluationRecord.now(
        experiment_id="e", run_id="r", circuit="sky130_common_source",
        method="random", seed=0, iteration=1, parameters={"x": 1.0},
        simulation_status="success", measurement_status="analysis_error",
        bandwidth_status="analysis_error", bandwidth_lower_bound_hz=None,
        failure_type="analysis_error", raw_metrics={}, objective_value=None,
        constraint_violation=None, simulation_time=0.1, total_elapsed_time=0.1,
        run_directory="runs/evaluation_0001", ngspice_called=True,
        error_message="unparseable physical response", ngspice_return_code=0,
    )
    assert record.simulation_status == "success"
    assert record.measurement_status == "analysis_error"
    assert record.ngspice_return_code == 0


def test_task3_frozen_hash_remains_unchanged() -> None:
    assert load_experiment_config(
        "research/common_source/common_source_frozen.yaml"
    ).computed_benchmark_hash() == TASK3_HASH


def test_all_four_optimizers_share_task4_hash() -> None:
    config = _task4_config()
    hashes = {replace(config, method=method).computed_benchmark_hash() for method in ("random", "de", "tpe", "bo")}
    assert len(hashes) == 1


def test_kaplan_meier_with_censoring_and_rmst() -> None:
    estimate = kaplan_meier([(2, True), (4, False), (4, True)], horizon=4)
    assert estimate.points[0].survival_probability == pytest.approx(2 / 3)
    assert estimate.points[-1].survival_probability == pytest.approx(1 / 3)
    assert estimate.rmst == pytest.approx(10 / 3)
    assert estimate.median_time_to_event == 4


@pytest.mark.integration
def test_real_sky130_ngspice_end_to_end(tmp_path: Path) -> None:
    config = _task4_config()
    parameters = {
        "width_m": 1.26e-6,
        "length_m": 0.15e-6,
        "drain_resistance_ohm": 10_000.0,
        "input_bias_v": 0.9,
    }
    calls: list[int] = []
    simulation = Sky130CommonSourceNgspiceSimulator(config).evaluate(
        parameters, tmp_path / "evaluation_0001", lambda: calls.append(1)
    )
    outcome = Sky130CommonSourceAnalyzer(config).extract(simulation, parameters)
    assert calls == [1]
    assert simulation.process.returncode == 0
    assert outcome.measurement_status == "complete"
    assert outcome.metrics["dc_power_w"] == pytest.approx(
        abs(
            simulation.operating_point.supply_voltage_v
            * simulation.operating_point.supply_current_a
        )
    )
    assert outcome.metrics["gm"] > 0
    assert simulation.log_path.is_file()
