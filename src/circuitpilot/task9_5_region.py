"""Task 9.5 counterfactual SKY130 operating-region classification.

The historical Task 7--9 classifier remains frozen.  SKY130's ngspice
subcircuit reports internal NMOS and PMOS operating voltages in positive,
type-normalized coordinates for this locked model tree; reverse VDS is not
turned positive by an absolute value.
"""

from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
from typing import Mapping


V1_SEMANTICS = "long_channel_proxy_v1"
V2_SEMANTICS = "model_consistent_saturation_v2"
V2_HEADROOM_TOLERANCE_V = 1e-6
QUANTITIES = ("vgs", "vds", "vth", "vdsat", "gm", "gds")


def region_semantics_hash(*, version: str, tolerance_v: float = V2_HEADROOM_TOLERANCE_V) -> str:
    if version not in (V1_SEMANTICS, V2_SEMANTICS):
        raise ValueError("unknown operating-region semantics")
    if not isfinite(tolerance_v) or tolerance_v < 0:
        raise ValueError("invalid headroom tolerance")
    definition = {
        "version": version,
        "on_rule": "type_normalized_vgs_above_vth_and_positive_gm" if version == V2_SEMANTICS
                   else "historical_vgs_above_vth",
        "headroom_rule": "vds_plus_tolerance_at_least_model_vdsat" if version == V2_SEMANTICS
                         else "historical_vds_at_least_vgs_minus_vth",
        "tolerance_v": tolerance_v if version == V2_SEMANTICS else 0.0,
        "pfet_sign_rule": "positive_ngspice_internal_coordinates_no_abs_reverse_vds"
                          if version == V2_SEMANTICS else "historical_absolute_magnitudes",
    }
    return sha256(json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def classify_device(
    values: Mapping[str, float], *, version: str,
    pfet: bool = False, tolerance_v: float = V2_HEADROOM_TOLERANCE_V,
) -> str:
    """Return saturation, off, triode, reverse, missing, or non_finite.

    `pfet` verifies the expected role, while ngspice's measured internal
    coordinates supply the sign convention for both transistor types.
    """
    if version not in (V1_SEMANTICS, V2_SEMANTICS):
        raise ValueError("unknown operating-region semantics")
    if not isfinite(tolerance_v) or tolerance_v < 0:
        raise ValueError("invalid headroom tolerance")
    required = ("vgs", "vds", "vth") if version == V1_SEMANTICS else QUANTITIES
    if not set(required) <= set(values):
        return "missing"
    if any(not isfinite(float(values[name])) for name in required):
        return "non_finite"
    # The locked SKY130 wrapper reports PFET quantities internally as positive
    # type-normalized values.  This is checked in the real probe and replay.
    vgs, vds, vth = (float(values[name]) for name in ("vgs", "vds", "vth"))
    if version == V1_SEMANTICS and pfet:
        overdrive = abs(vgs) - abs(vth)
        if overdrive <= 0:
            return "off"
        return "saturation" if abs(vds) >= overdrive else "triode"
    if pfet and (vgs < 0 or vth < 0):
        return "invalid_pfet_convention"
    if vgs <= vth:
        return "off"
    if vds < 0:
        return "reverse"
    if version == V1_SEMANTICS:
        return "saturation" if vds >= vgs - vth else "triode"
    vdsat = float(values["vdsat"])
    if vdsat < 0 or float(values["gm"]) <= 0 or float(values["gds"]) < 0:
        return "invalid_model_evidence"
    return "saturation" if vds + tolerance_v >= vdsat else "triode"


def classify_devices(
    devices: Mapping[str, Mapping[str, float]], *, version: str,
    pfet_roles: frozenset[str],
) -> dict[str, str]:
    return {
        role: classify_device(values, version=version, pfet=role in pfet_roles)
        for role, values in devices.items()
    }
