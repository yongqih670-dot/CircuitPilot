"""Model VDSAT and polarity regression tests for Task 9.5."""

from circuitpilot.task9_5_region import (
    V1_SEMANTICS, V2_SEMANTICS, classify_device, region_semantics_hash,
)


def q(**overrides):
    values = {"vgs": 0.9, "vds": 0.15, "vth": 0.6,
              "vdsat": 0.12, "gm": 1e-4, "gds": 1e-6}
    values.update(overrides)
    return values


def test_vdsat_evidence_changes_nmos_classification() -> None:
    assert classify_device(q(), version=V1_SEMANTICS) == "triode"
    assert classify_device(q(), version=V2_SEMANTICS) == "saturation"
    assert classify_device(q(vds=0.10), version=V2_SEMANTICS) == "triode"


def test_pmos_uses_internal_positive_coordinates_without_abs_reverse_vds() -> None:
    assert classify_device(q(vgs=1.1, vth=0.7, vds=0.2, vdsat=0.18),
                           version=V2_SEMANTICS, pfet=True) == "saturation"
    assert classify_device(q(vds=-0.2), version=V2_SEMANTICS, pfet=True) == "reverse"
    assert classify_device(q(vgs=-1.1), version=V2_SEMANTICS, pfet=True) == "invalid_pfet_convention"


def test_off_missing_and_tolerance_boundary() -> None:
    assert classify_device(q(vgs=0.5), version=V2_SEMANTICS) == "off"
    assert classify_device({"vgs": 0.9}, version=V2_SEMANTICS) == "missing"
    assert classify_device(q(vds=0.1199995), version=V2_SEMANTICS) == "saturation"
    assert classify_device(q(vds=0.119998), version=V2_SEMANTICS) == "triode"


def test_semantics_hash_changes_with_version_and_tolerance() -> None:
    assert region_semantics_hash(version=V1_SEMANTICS) != region_semantics_hash(version=V2_SEMANTICS)
    assert region_semantics_hash(version=V2_SEMANTICS, tolerance_v=0) != region_semantics_hash(version=V2_SEMANTICS)
