from dataclasses import replace
from pathlib import Path

import pytest

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.exceptions import NetlistError, ParseError
from circuitpilot.parser import ACAnalysisResult
from circuitpilot.sky130_two_stage_ota import (
    DEVICE_ROLE_MAPPING,
    DEVICE_ROLES,
    PhaseMarginStatus,
    SlewStatus,
    TASK7_PARAMETER_NAMES,
    TransientResponse,
    UgfStatus,
    assess_task7_operating_regions,
    generate_task7_ac_netlist,
    generate_task7_op_netlist,
    generate_task7_transient_netlist,
    measure_task7_slew,
    measure_task7_stability,
    parse_task7_operating_point,
    parse_task7_transient,
)


FROZEN = Path("research/sky130/two_stage_ota/task7_frozen.yaml")


@pytest.fixture(scope="module")
def circuit():
    return load_experiment_config(FROZEN).circuit_config


@pytest.fixture
def parameters():
    return {
        "input_pair_width_m": 8e-6,
        "input_pair_length_m": 0.5e-6,
        "first_stage_load_width_m": 12e-6,
        "first_stage_load_length_m": 0.6e-6,
        "tail_width_m": 8e-6,
        "tail_length_m": 0.6e-6,
        "second_stage_width_m": 20e-6,
        "second_stage_length_m": 0.5e-6,
        "second_load_width_m": 20e-6,
        "second_load_length_m": 0.5e-6,
        "second_load_bias_v": 0.8,
        "compensation_capacitance_f": 1e-12,
    }


def _paths():
    return {
        "invariant_path": "invariant.spice",
        "nfet_corner_path": "nfet.corner.spice",
        "pfet_corner_path": "pfet.corner.spice",
    }


def test_frozen_config_loads_and_has_twelve_dimensions():
    config = load_experiment_config(FROZEN)
    assert config.circuit_name == "sky130_two_stage_ota"
    assert len(config.search_space) == 12
    assert set(config.search_space_by_name) == TASK7_PARAMETER_NAMES


def test_all_device_roles_have_explicit_four_terminal_mapping():
    assert len(DEVICE_ROLES) == 7
    assert all(len(DEVICE_ROLE_MAPPING[role]["nodes"]) == 4 for role in DEVICE_ROLES)


def test_op_netlist_contains_seven_real_sky130_devices(circuit, parameters):
    text = generate_task7_op_netlist(
        circuit,
        parameters,
        **_paths(),
        op_output_path="op.dat",
        device_op_output_path="devices.dat",
    )
    assert sum(text.count(f"XM{index} ") for index in range(1, 8)) == 7
    assert "sky130_fd_pr__nfet_01v8" in text
    assert "sky130_fd_pr__pfet_01v8" in text
    assert "@m.xm7.msky130_fd_pr__pfet_01v8[vdsat]" in text


def test_ac_netlist_uses_unit_differential_and_degree_conversion(circuit, parameters):
    text = generate_task7_ac_netlist(
        circuit,
        parameters,
        **_paths(),
        ac_output_path="ac.dat",
        start_frequency_hz=10,
        stop_frequency_hz=1e10,
        points_per_decade=30,
    )
    assert "AC 0.5 0" in text
    assert "AC 0.5 180" in text
    assert "180/pi*vp(vout)" in text


def test_transient_netlist_is_unity_follower_with_fixed_edges(circuit, parameters):
    text = generate_task7_transient_netlist(
        circuit,
        parameters,
        **_paths(),
        transient_output_path="tran.dat",
    )
    assert "VFB vin_minus vout 0" in text
    assert "PULSE(0.8 1" in text
    assert "tran 2e-09 4e-06 0 2e-09" in text


def test_netlist_rejects_missing_parameter(circuit, parameters):
    parameters.pop("tail_width_m")
    with pytest.raises(NetlistError):
        generate_task7_op_netlist(
            circuit,
            parameters,
            **_paths(),
            op_output_path="op.dat",
            device_op_output_path="devices.dat",
        )


def test_netlist_rejects_invalid_ac_window(circuit, parameters):
    with pytest.raises(NetlistError):
        generate_task7_ac_netlist(
            circuit,
            parameters,
            **_paths(),
            ac_output_path="ac.dat",
            start_frequency_hz=10,
            stop_frequency_hz=10,
            points_per_decade=30,
        )


def _write_operating_point(tmp_path, overrides=None):
    op = tmp_path / "op.dat"
    devices = tmp_path / "devices.dat"
    op.write_text("header\n1.8 .9 .9 .8 .9 .2 .72 .8 -1e-4\n", encoding="utf-8")
    raw = []
    overrides = overrides or {}
    for role in DEVICE_ROLES:
        values = (
            [-1.0, -0.8, 1e-3, 1e-5, -0.4, -0.2]
            if role in {"load_mirror", "load_first", "second_load"}
            else [1.0, 0.8, 1e-3, 1e-5, 0.4, 0.2]
        )
        values = overrides.get(role, values)
        raw.extend(values)
    devices.write_text(" ".join(str(value) for value in raw) + "\n", encoding="utf-8")
    return op, devices


def test_operating_point_parser_exposes_power_and_all_device_vectors(tmp_path):
    op, devices = _write_operating_point(tmp_path)
    result = parse_task7_operating_point(op, devices)
    assert result.dc_power_w == pytest.approx(1.8e-4)
    assert set(result.device_quantities) == set(DEVICE_ROLES)
    assert set(result.device_quantities["input_plus"]) == {
        "vgs",
        "vds",
        "gm",
        "gds",
        "vth",
        "vdsat",
    }


def test_operating_point_parser_rejects_short_device_vector(tmp_path):
    op, devices = _write_operating_point(tmp_path)
    devices.write_text("1 2 3\n", encoding="utf-8")
    with pytest.raises(ParseError):
        parse_task7_operating_point(op, devices)


def test_all_saturated_devices_are_valid(tmp_path):
    op, devices = _write_operating_point(tmp_path)
    assessment = assess_task7_operating_regions(
        parse_task7_operating_point(op, devices)
    )
    assert assessment.valid
    assert assessment.violation_mask == 0


def test_nmos_off_has_explicit_taxonomy(tmp_path):
    op, devices = _write_operating_point(
        tmp_path, {"tail": [0.3, 0.8, 1e-3, 1e-5, 0.4, 0.2]}
    )
    assessment = assess_task7_operating_regions(
        parse_task7_operating_point(op, devices)
    )
    assert assessment.device_status["tail"] == "off"
    assert "tail:off" in assessment.violation_types


def test_pmos_triode_has_explicit_taxonomy(tmp_path):
    op, devices = _write_operating_point(
        tmp_path, {"second_load": [-1.0, -0.2, 1e-3, 1e-5, -0.4, -0.2]}
    )
    assessment = assess_task7_operating_regions(
        parse_task7_operating_point(op, devices)
    )
    assert assessment.device_status["second_load"] == "triode"


def test_stability_measures_log_interpolated_ugf_and_same_phase():
    response = ACAnalysisResult(
        frequency_hz=(1e3, 1e4, 1e5),
        gain_db=(20.0, 4.0, -4.0),
        phase_deg=(-5.0, -80.0, -120.0),
    )
    result = measure_task7_stability(response)
    assert result.ugf_status is UgfStatus.MEASURED
    assert result.ugf_hz == pytest.approx(10 ** 4.5)
    assert result.phase_margin_deg == pytest.approx(80.0)


def test_stability_unwraps_phase_before_margin():
    response = ACAnalysisResult(
        frequency_hz=(1e3, 1e4, 1e5),
        gain_db=(20.0, 2.0, -2.0),
        phase_deg=(-5.0, -170.0, 170.0),
    )
    result = measure_task7_stability(response)
    assert result.unwrapped_phase_deg == pytest.approx((-5.0, -170.0, -190.0))
    assert result.phase_margin_deg == pytest.approx(0.0)


def test_stability_counts_multiple_descending_crossings():
    response = ACAnalysisResult(
        frequency_hz=(1, 10, 100, 1000, 10000),
        gain_db=(3, -1, 2, -2, -3),
        phase_deg=(0, -40, -60, -100, -120),
    )
    result = measure_task7_stability(response)
    assert result.crossing_count == 2
    assert result.message == "2 descending crossings; first selected"


def test_stability_right_censoring_has_lower_bound():
    response = ACAnalysisResult((1, 10, 100), (30, 20, 3), (0, -20, -60))
    result = measure_task7_stability(response)
    assert result.ugf_status is UgfStatus.RIGHT_CENSORED
    assert result.ugf_lower_bound_hz == 100
    assert result.phase_margin_status is PhaseMarginStatus.UNAVAILABLE


def test_stability_low_gain_has_no_crossing():
    response = ACAnalysisResult((1, 10), (-1, -2), (0, -20))
    assert measure_task7_stability(response).ugf_status is UgfStatus.NO_CROSSING


def test_stability_rejects_wrong_low_frequency_polarity():
    response = ACAnalysisResult((1, 10), (10, -1), (179, 150))
    assert measure_task7_stability(response).ugf_status is UgfStatus.INVALID_RESPONSE


def test_transient_parser_requires_increasing_time(tmp_path):
    path = tmp_path / "tran.dat"
    path.write_text("0 .8 .8\n1e-9 .8 .81\n1e-9 .8 .82\n", encoding="utf-8")
    with pytest.raises(ParseError):
        parse_task7_transient(path)


def test_slew_uses_fixed_interpolated_crossings(circuit):
    response = TransientResponse(
        time_s=(0, 0.51e-6, 0.61e-6, 0.71e-6, 2.01e-6, 2.11e-6, 2.21e-6),
        command_v=(0.8, 1, 1, 1, 0.8, 0.8, 0.8),
        output_v=(0.8, 0.8, 0.84, 0.96, 1.0, 0.96, 0.84),
    )
    result = measure_task7_slew(response, circuit)
    assert result.positive_status is SlewStatus.MEASURED
    assert result.negative_status is SlewStatus.MEASURED
    assert result.positive_slew_v_per_s == pytest.approx(1.2e6)
    assert result.negative_slew_v_per_s == pytest.approx(1.2e6)


def test_slew_reports_insufficient_transition(circuit):
    response = TransientResponse(
        time_s=(0, 0.6e-6, 1e-6, 2.1e-6, 3e-6),
        command_v=(0.8, 1, 1, 0.8, 0.8),
        output_v=(0.8, 0.82, 0.83, 0.83, 0.81),
    )
    result = measure_task7_slew(response, circuit)
    assert result.positive_status is SlewStatus.INSUFFICIENT_TRANSITION
    assert result.negative_status is SlewStatus.INSUFFICIENT_TRANSITION


def test_config_rejects_changed_semantic_version(circuit):
    with pytest.raises(ValueError):
        replace(circuit, ugf_semantics_version="changed")
