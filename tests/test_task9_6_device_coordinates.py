import pytest

from circuitpilot.task9_6_device_coordinates import (
    GM_OVER_ID_CURRENT_FLOOR_A, gm_over_id, preserve_device_coordinates,
)


MODEL = {"vgs": 0.68, "vds": 0.9, "vth": 0.69,
         "vdsat": 0.08, "gm": 2e-4, "gds": 1e-6}


def test_nfet_external_signed_coordinates_remain_distinct_from_model_internal():
    outcome = preserve_device_coordinates(
        "input_minus", {"mirror": 1.1, "vin_minus": 0.9,
                        "tail": 0.3, "gnd": 0.0}, MODEL,
        model_id_raw_a=2e-5)
    assert outcome["external_signed_vgs_v"] == pytest.approx(0.6)
    assert outcome["external_vgs_n_v"] == pytest.approx(0.6)
    assert outcome["external_vds_n_v"] == pytest.approx(0.8)
    assert outcome["model_internal_raw"]["vgs"] == 0.68
    assert outcome["model_internal_on_margin_v"] < 0
    assert outcome["benchmark_on_condition_pass"] is False
    assert outcome["model_saturation_condition_pass"] is True
    assert outcome["gm_over_id_status"] == "valid"


def test_pfet_external_vgs_vds_keep_negative_sign_and_oriented_vsg_vsd():
    outcome = preserve_device_coordinates(
        "load_first", {"stage1_out": 0.8, "mirror": 0.95,
                       "vdd": 1.8}, MODEL, model_id_raw_a=-2e-5)
    assert outcome["external_signed_vgs_v"] < 0
    assert outcome["external_signed_vds_v"] < 0
    assert outcome["external_vsg_p_v"] > 0
    assert outcome["external_vsd_p_v"] > 0
    assert outcome["gm_over_id_inv_v"] == 10.0


def test_gm_over_id_rejects_near_zero_current():
    assert gm_over_id(1e-4, GM_OVER_ID_CURRENT_FLOOR_A) == (
        None, "invalid_near_zero_current")
    assert gm_over_id(1e-4, None) == (None, "not_measured")
