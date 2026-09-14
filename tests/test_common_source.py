from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from circuitpilot.common_source import (
    CommonSourceCircuitConfig,
    analyze_common_source,
    generate_common_source_netlist,
    parse_operating_point,
)
from circuitpilot.exceptions import ConfigError
from circuitpilot.experiments.config import (
    ConstraintDefinition,
    ConstraintOperator,
    ExperimentConfig,
    NgspiceConfig,
    ObjectiveDefinition,
    ObjectiveType,
    ParameterType,
    SearchParameter,
    SuccessCriterion,
)
from circuitpilot.experiments.objectives import ObjectiveEvaluator
from circuitpilot.mosfet_model import MosfetModelConfig
from circuitpilot.parser import ACAnalysisResult


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "research" / "models" / "ngspice_bsim3_nmos.lib"


def model_config(path: Path = MODEL_PATH) -> MosfetModelConfig:
    return MosfetModelConfig(
        path,
        "N1",
        "reference",
        "ngspice 46 examples/mos/modelcard.nmos",
    )


def circuit_config(path: Path = MODEL_PATH) -> CommonSourceCircuitConfig:
    return CommonSourceCircuitConfig(1.8, 1e-12, 27.0, model_config(path))


def experiment_config(tmp_path: Path) -> ExperimentConfig:
    spaces = (
        SearchParameter("width_m", ParameterType.FLOAT, 1e-6, 100e-6, True, unit="m", technology_low=0.5e-6, technology_high=200e-6),
        SearchParameter("length_m", ParameterType.FLOAT, 0.5e-6, 2e-6, False, unit="m", technology_low=0.3e-6, technology_high=10e-6),
        SearchParameter("drain_resistance_ohm", ParameterType.FLOAT, 1e3, 100e3, True, unit="ohm", technology_low=100.0, technology_high=1e6),
        SearchParameter("input_bias_v", ParameterType.FLOAT, 0.6, 1.4, False, unit="V", technology_low=0.0, technology_high=1.8),
    )
    constraints = (
        ConstraintDefinition("gain_db", ConstraintOperator.GREATER_EQUAL, 8.0, constraint_id="gain_min"),
        ConstraintDefinition("bandwidth_hz", ConstraintOperator.GREATER_EQUAL, 1e6, constraint_id="bandwidth_min"),
        ConstraintDefinition("dc_power_w", ConstraintOperator.LESS_EQUAL, 2e-4, constraint_id="power_max"),
        ConstraintDefinition("output_dc_voltage", ConstraintOperator.GREATER_EQUAL, 0.36, constraint_id="output_bias_low"),
        ConstraintDefinition("output_dc_voltage", ConstraintOperator.LESS_EQUAL, 1.44, constraint_id="output_bias_high"),
    )
    return ExperimentConfig(
        experiment_name="common_source_test",
        circuit_name="common_source",
        method="random",
        seed=0,
        simulation_budget=1,
        output_dir=tmp_path,
        search_space=spaces,
        objectives=(ObjectiveDefinition("dc_power_w", ObjectiveType.MINIMIZE),),
        constraints=constraints,
        success_criterion=SuccessCriterion(None, None, "all_constraints"),
        ngspice_config=NgspiceConfig(stop_frequency_hz=1e9, points_per_decade=30),
        circuit_config=circuit_config(),
    )


def test_missing_model_is_explicit_failure(tmp_path: Path) -> None:
    missing = model_config(tmp_path / "missing.lib")
    with pytest.raises(ConfigError, match="will not substitute"):
        missing.require_library()


def test_common_source_netlist_contains_real_op_ac_and_supply_current() -> None:
    text = generate_common_source_netlist(
        circuit_config(),
        {
            "width_m": 20e-6,
            "length_m": 1e-6,
            "drain_resistance_ohm": 10e3,
            "input_bias_v": 0.9,
        },
        ac_output_path="ac.dat",
        op_output_path="op.dat",
        device_op_output_path="device.dat",
        start_frequency_hz=10.0,
        stop_frequency_hz=1e9,
        points_per_decade=30,
    )
    assert ".include" in text
    assert ".model" not in text
    assert "op\n" in text
    assert "i(vdd)" in text
    assert "ac dec 30 10 1000000000" in text
    assert "M1 out in 0 0 N1 W=2e-05 L=1e-06" in text


def test_op_parser_and_real_supply_power(tmp_path: Path) -> None:
    op = tmp_path / "op.dat"
    device = tmp_path / "device.dat"
    op.write_text(
        "vdd v(vdd) v(in) v(out) i(vdd)\n"
        "1.8 1.8 0.9 1.30503944 -4.94960561e-05\n",
        encoding="utf-8",
    )
    device.write_text(
        "vdd vgs vds gm gds vth vdsat\n"
        "1.8 0.9 1.30503944 3.52597178e-4 2.48953337e-6 0.639893325 0.219371388\n",
        encoding="utf-8",
    )
    parsed = parse_operating_point(op, device)
    response = ACAnalysisResult(
        (10.0, 1e6, 1e7, 1e8),
        (10.7319862, 10.70, 9.5, 0.0),
        (-180.0, -181.0, -190.0, -250.0),
    )
    metrics = analyze_common_source(response, parsed)
    assert metrics.dc_power_w == pytest.approx(abs(1.8 * -4.94960561e-05))
    assert metrics.output_dc_voltage == pytest.approx(1.30503944)
    assert metrics.bandwidth_3db_hz > 1e7
    assert parsed.device_quantities["gm"] == pytest.approx(3.52597178e-4)


def test_normalized_constraints_and_all_constraint_feasibility(tmp_path: Path) -> None:
    evaluator = ObjectiveEvaluator(experiment_config(tmp_path))
    feasible = evaluator.evaluate(
        {"gain_db": 10.0, "bandwidth_hz": 2e6, "dc_power_w": 1e-4, "output_dc_voltage": 0.9}
    )
    assert feasible.is_feasible is True
    assert 0.0 <= feasible.objective_value < 1.0
    failed = evaluator.evaluate(
        {"gain_db": 4.0, "bandwidth_hz": 0.5e6, "dc_power_w": 3e-4, "output_dc_voltage": 1.6}
    )
    assert failed.is_feasible is False
    assert failed.constraint_components["gain_min"] == pytest.approx(0.5)
    assert failed.constraint_components["bandwidth_min"] == pytest.approx(0.5)
    assert failed.constraint_components["power_max"] == pytest.approx(0.5)
    assert failed.constraint_components["output_bias_high"] == pytest.approx((1.6 - 1.44) / 1.44)
    assert failed.objective_value == pytest.approx(1.0 + failed.constraint_violation)


def test_frozen_benchmark_hash_changes_with_semantics(tmp_path: Path) -> None:
    config = experiment_config(tmp_path)
    original = config.computed_benchmark_hash()
    changed = replace(
        config,
        circuit_config=replace(config.circuit_config, load_capacitance_f=2e-12),
    )
    assert changed.computed_benchmark_hash() != original
