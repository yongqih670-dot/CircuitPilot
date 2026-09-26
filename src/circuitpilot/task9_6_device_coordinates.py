"""Preserve external terminal signs and model-oriented v2 device evidence."""

from __future__ import annotations

from math import isfinite
from typing import Mapping

from circuitpilot.sky130_two_stage_ota import DEVICE_ROLE_MAPPING, PFET_ROLES
from circuitpilot.task9_5_region import V2_HEADROOM_TOLERANCE_V


GM_OVER_ID_CURRENT_FLOOR_A = 1e-12


def gm_over_id(gm_siemens: float | None, id_raw_a: float | None) -> tuple[float | None, str]:
    """Use gm/abs(Id); never divide by a near-zero current."""
    if gm_siemens is None or id_raw_a is None:
        return None, "not_measured"
    gm, current = float(gm_siemens), float(id_raw_a)
    if not isfinite(gm) or not isfinite(current) or gm < 0:
        return None, "invalid_nonfinite_or_negative_gm"
    if abs(current) <= GM_OVER_ID_CURRENT_FLOOR_A:
        return None, "invalid_near_zero_current"
    return gm / abs(current), "valid"


def preserve_device_coordinates(
    role: str,
    node_voltages_v: Mapping[str, float],
    model_quantities: Mapping[str, float],
    *,
    model_id_raw_a: float | None,
) -> dict[str, object]:
    """Do not overwrite external VGS/VDS with SKY130 internal model values."""
    if role not in DEVICE_ROLE_MAPPING:
        raise ValueError(f"unknown device role: {role}")
    mapping = DEVICE_ROLE_MAPPING[role]
    drain, gate, source, bulk = mapping["nodes"]
    nodes = dict(node_voltages_v)
    nodes.setdefault("gnd", 0.0)
    required = {drain, gate, source, bulk}
    if not required <= nodes.keys():
        raise ValueError(f"missing external node voltage for {role}: {required - nodes.keys()}")
    if any(not isfinite(float(nodes[name])) for name in required):
        raise ValueError("nonfinite external terminal voltage")
    expected = {"vgs", "vds", "vth", "vdsat", "gm", "gds"}
    if not expected <= model_quantities.keys():
        raise ValueError(f"missing model operating-point quantity for {role}")
    model = {name: float(model_quantities[name]) for name in expected}
    if any(not isfinite(value) for value in model.values()):
        raise ValueError("nonfinite model operating-point quantity")
    vg, vd, vs, vb = (float(nodes[name]) for name in (gate, drain, source, bulk))
    external_vgs = vg - vs
    external_vds = vd - vs
    external_vbs = vb - vs
    pfet = role in PFET_ROLES
    normalized_gate = vs - vg if pfet else external_vgs
    normalized_drain = vs - vd if pfet else external_vds
    ratio, ratio_status = gm_over_id(model["gm"], model_id_raw_a)
    benchmark_on = model["vgs"] > model["vth"] and model["gm"] > 0
    model_saturation = (model["vds"] >= 0 and model["vdsat"] >= 0
                        and model["vds"] + V2_HEADROOM_TOLERANCE_V >= model["vdsat"])
    return {
        "role": role,
        "device_type": "pfet" if pfet else "nfet",
        "external_terminal_nodes": {"drain": drain, "gate": gate,
                                    "source": source, "bulk": bulk},
        "external_terminal_voltages_v": {"drain": vd, "gate": vg,
                                         "source": vs, "bulk": vb},
        "external_signed_vgs_v": external_vgs,
        "external_signed_vds_v": external_vds,
        "external_signed_vbs_v": external_vbs,
        "external_device_oriented_gate_v": normalized_gate,
        "external_device_oriented_drain_v": normalized_drain,
        "external_vsg_p_v": normalized_gate if pfet else None,
        "external_vsd_p_v": normalized_drain if pfet else None,
        "external_vgs_n_v": normalized_gate if not pfet else None,
        "external_vds_n_v": normalized_drain if not pfet else None,
        "model_internal_raw": model,
        "model_internal_on_margin_v": model["vgs"] - model["vth"],
        "model_internal_vdsat_headroom_v": model["vds"] - model["vdsat"],
        "benchmark_on_condition_pass": benchmark_on,
        "model_saturation_condition_pass": model_saturation,
        "model_id_raw_a": model_id_raw_a,
        "gm_over_id_inv_v": ratio,
        "gm_over_id_status": ratio_status,
    }
