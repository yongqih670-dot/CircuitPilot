from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from math import inf
from pathlib import Path

import pytest

from circuitpilot.bandwidth import BandwidthStatus, measure_bandwidth
from circuitpilot.experiments.analyzer import Sky130DifferentialAmplifierAnalyzer
from circuitpilot.experiments.calibration import generate_sobol_candidates
from circuitpilot.experiments.config import (
    ConstraintDefinition,
    ConstraintOperator,
    load_experiment_config,
)
from circuitpilot.experiments.objectives import ObjectiveEvaluator
from circuitpilot.experiments.simulation import (
    Sky130DifferentialAmplifierNgspiceSimulator,
)
from circuitpilot.sky130_differential_amplifier import (
    CMRR_SEMANTICS_VERSION,
    CmrrStatus,
    device_operating_region_valid,
    generate_sky130_differential_amplifier_netlist,
    measure_cmrr,
)


TASK4_HASH = "1a577200d71a900eb8ffec3fe680e3dd53e0298e87692dc66f407481de46c664"
TASK5_HASH = "57d2183621ecf37e5ca22e012452c43fce6459be7d347a5cfc93d0b394c14378"


def _config():
    return load_experiment_config(
        "research/sky130/differential_amplifier/calibration_config.yaml"
    )


def _parameters():
    return {
        "input_pair_width_m": 3e-6,
        "input_pair_length_m": 0.3e-6,
        "active_load_width_m": 6e-6,
        "active_load_length_m": 0.5e-6,
        "tail_width_m": 4e-6,
        "tail_length_m": 0.5e-6,
        "tail_bias_v": 0.75,
    }


def _netlist() -> str:
    return generate_sky130_differential_amplifier_netlist(
        _config().circuit_config,
        _parameters(),
        invariant_path="P:/invariant.spice",
        nfet_corner_path="P:/nfet.spice",
        pfet_corner_path="P:/pfet.spice",
        differential_ac_output_path="R:/diff.dat",
        common_mode_ac_output_path="R:/common.dat",
        op_output_path="R:/op.dat",
        device_op_output_path="R:/device.dat",
        start_frequency_hz=10.0,
        stop_frequency_hz=1e10,
        points_per_decade=30,
    )


def test_nmos_differential_pair_topology() -> None:
    text = _netlist()
    assert "XDM1 mirror_D inp_D tail_D 0 sky130_fd_pr__nfet_01v8" in text
    assert "XDM2 out_D inn_D tail_D 0 sky130_fd_pr__nfet_01v8" in text


def test_pmos_current_mirror_active_load_topology() -> None:
    text = _netlist()
    assert "XDL1 mirror_D mirror_D vdd_D vdd_D sky130_fd_pr__pfet_01v8" in text
    assert "XDL2 out_D mirror_D vdd_D vdd_D sky130_fd_pr__pfet_01v8" in text


def test_all_bulk_terminals_are_explicit() -> None:
    text = _netlist()
    assert "tail_D 0 sky130_fd_pr__nfet_01v8" in text
    assert "vdd_D vdd_D sky130_fd_pr__pfet_01v8" in text
    assert "tail_source_D 0 sky130_fd_pr__nfet_01v8" in text


def test_matched_role_mapping_forces_equal_dimensions() -> None:
    text = _netlist()
    input_lines = [line for line in text.splitlines() if line.startswith(("XDM1 ", "XDM2 "))]
    load_lines = [line for line in text.splitlines() if line.startswith(("XDL1 ", "XDL2 "))]
    assert {line.split(" W=", 1)[1] for line in input_lines} == {"3 L=0.3"}
    assert {line.split(" W=", 1)[1] for line in load_lines} == {"6 L=0.5"}


def test_differential_mode_testbench_is_unit_differential() -> None:
    text = _netlist()
    assert "VINP_D inp_D 0 DC 0.9 AC 0.5 0" in text
    assert "VINN_D inn_D 0 DC 0.9 AC 0.5 180" in text
    assert "wrdata R:/diff.dat vdb(out_D) vp(out_D)" in text


def test_common_mode_testbench_is_direct_equal_excitation() -> None:
    text = _netlist()
    assert "VINP_C inp_C 0 DC 0.9 AC 1 0" in text
    assert "VINN_C inn_C 0 DC 0.9 AC 1 0" in text
    assert "wrdata R:/common.dat vdb(out_C) vp(out_C)" in text


def test_cmrr_exact_extraction() -> None:
    result = measure_cmrr(40.0, -20.0, common_mode_gain_floor_db=-120.0)
    assert result.status is CmrrStatus.MEASURED
    assert result.cmrr_db == 60.0
    assert result.lower_bound_db is None


def test_cmrr_numerical_edge_case_is_invalid_not_infinite() -> None:
    result = measure_cmrr(40.0, -inf, common_mode_gain_floor_db=-120.0)
    assert result.status is CmrrStatus.INVALID
    assert result.cmrr_db is None


def test_cmrr_lower_bound_semantics() -> None:
    result = measure_cmrr(35.0, -125.0, common_mode_gain_floor_db=-120.0)
    assert result.status is CmrrStatus.LOWER_BOUND
    assert result.cmrr_db is None
    assert result.lower_bound_db == 155.0


def test_cmrr_lower_bound_can_satisfy_constraint() -> None:
    config = replace(
        _config(),
        constraints=(
            ConstraintDefinition("cmrr_db", ConstraintOperator.GREATER_EQUAL, 80.0),
        ),
    )
    result = ObjectiveEvaluator(config).evaluate(
        {"dc_power_w": 1e-4, "cmrr_db": None},
        cmrr_status="lower_bound",
        cmrr_lower_bound_db=100.0,
    )
    assert result.is_feasible


def test_differential_bandwidth_right_censoring_is_reused() -> None:
    result = measure_bandwidth((1.0, 10.0, 100.0), (20.0, 19.5, 19.0))
    assert result.bandwidth_status is BandwidthStatus.RIGHT_CENSORED
    assert result.bandwidth_hz is None
    assert result.bandwidth_lower_bound_hz == 100.0


def test_nmos_and_pmos_operating_region_physics() -> None:
    assert device_operating_region_valid(
        "input_m1", {"vgs": 0.8, "vds": 0.5, "vth": 0.6}
    )
    assert device_operating_region_valid(
        "load_mirror", {"vgs": 1.0, "vds": 1.0, "vth": 0.8}
    )
    assert not device_operating_region_valid(
        "tail", {"vgs": 0.7, "vds": 0.01, "vth": 0.6}
    )


def test_candidate_cost_accounting_is_frozen() -> None:
    config = _config()
    definition = config.circuit_config.to_dict()["simulation_cost_definition"]
    assert definition["primary_budget_unit"] == "candidate_evaluation"
    assert definition["ngspice_process_calls_per_candidate"] == 1
    assert definition["physical_analysis_calls_per_candidate"] == 2
    text = _netlist()
    assert text.count("\nop\n") == 1
    assert text.count("\nac dec ") == 1


def test_sobol_calibration_is_deterministic_and_in_bounds() -> None:
    config = _config()
    first = generate_sobol_candidates(config, count=8, scramble=False, seed=0)
    second = generate_sobol_candidates(config, count=8, scramble=False, seed=0)
    assert first == second
    assert len(first) == 8
    for candidate in first:
        config.validate_parameters(candidate)


def test_benchmark_hash_changes_if_topology_changes() -> None:
    config = _config()
    changed_circuit = deepcopy(config.circuit_config)
    object.__setattr__(changed_circuit, "topology_version", "tampered_topology")
    changed = replace(config, circuit_config=changed_circuit)
    assert changed.computed_benchmark_hash() != config.computed_benchmark_hash()


def test_benchmark_hash_changes_if_cmrr_semantics_change() -> None:
    config = _config()
    assert config.circuit_config.cmrr_semantics_version == CMRR_SEMANTICS_VERSION
    changed_circuit = deepcopy(config.circuit_config)
    object.__setattr__(changed_circuit, "cmrr_semantics_version", "tampered_cmrr")
    changed = replace(config, circuit_config=changed_circuit)
    assert changed.computed_benchmark_hash() != config.computed_benchmark_hash()


def test_task4_frozen_hash_remains_unchanged() -> None:
    assert load_experiment_config(
        "research/sky130/common_source/sky130_common_source_frozen.yaml"
    ).computed_benchmark_hash() == TASK4_HASH


def test_task5_frozen_hash_is_independent() -> None:
    config = load_experiment_config(
        "research/sky130/differential_amplifier/differential_amplifier_frozen.yaml"
    )
    assert config.computed_benchmark_hash() == TASK5_HASH
    assert TASK5_HASH != TASK4_HASH


def test_all_four_optimizers_share_task5_hash() -> None:
    paths = (
        "experiments/configs/sky130_differential_random.yaml",
        "experiments/configs/sky130_differential_de.yaml",
        "experiments/configs/sky130_differential_tpe.yaml",
        "experiments/configs/sky130_differential_bo.yaml",
    )
    hashes = {load_experiment_config(path).computed_benchmark_hash() for path in paths}
    assert hashes == {TASK5_HASH}


@pytest.mark.integration
def test_real_sky130_differential_amplifier_end_to_end(tmp_path: Path) -> None:
    config = _config()
    calls: list[int] = []
    simulation = Sky130DifferentialAmplifierNgspiceSimulator(config).evaluate(
        _parameters(), tmp_path, lambda: calls.append(1)
    )
    outcome = Sky130DifferentialAmplifierAnalyzer(config).extract(
        simulation, _parameters()
    )
    assert calls == [1]
    assert simulation.process.returncode == 0
    assert simulation.analysis_calls == 2
    assert simulation.ngspice_process_calls == 1
    assert outcome.measurement_status == "complete"
    assert outcome.metrics["differential_gain_db"] == pytest.approx(34.3827191)
    assert outcome.metrics["common_mode_gain_db"] == pytest.approx(-21.7283876)
    assert outcome.metrics["cmrr_db"] == pytest.approx(56.1111067)
    assert outcome.metrics["tail_current_a"] > 0
    assert outcome.metrics["dc_power_w"] == pytest.approx(
        abs(
            simulation.operating_point.supply_voltage_v
            * simulation.operating_point.supply_current_a
        )
    )
    assert outcome.metrics["operating_region_valid"] == 1.0
