"""Explicit power metric models for RC and future transistor-level circuits."""

from __future__ import annotations

import cmath
from math import isfinite, radians

from circuitpilot.circuit_config import CircuitType


DERIVED_RC_POWER_METRIC = "derived_rc_power"
DC_SUPPLY_POWER_METRIC = "dc_supply_power"


def derived_rc_power(
    *,
    gain_db: float,
    phase_deg: float,
    resistance_ohm: float,
    circuit_type: CircuitType,
) -> float:
    """Return the existing ideal RC resistor-power estimate in watts.

    This compatibility model derives power from an ngspice transfer-function
    sample for a 1 V peak AC source. It is intentionally named separately from
    transistor-level DC supply power so research records cannot conflate them.
    """
    values = (gain_db, phase_deg, resistance_ohm)
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
        for value in values
    ):
        raise ValueError("RC power inputs must be finite numbers")
    if resistance_ohm <= 0:
        raise ValueError("resistance_ohm must be positive")
    if circuit_type not in {CircuitType.RC_LOWPASS, CircuitType.RC_HIGHPASS}:
        raise ValueError("derived_rc_power supports only RC low-pass and high-pass")

    transfer = cmath.rect(10.0 ** (gain_db / 20.0), radians(phase_deg))
    resistor_voltage = (
        1.0 - transfer
        if circuit_type is CircuitType.RC_LOWPASS
        else transfer
    )
    return abs(resistor_voltage) ** 2 / (2.0 * resistance_ohm)


def dc_supply_power(supply_voltage_v: float, supply_current_a: float) -> float:
    """Return transistor-level DC supply power as ``abs(VDD * I(VDD))``.

    ngspice reports current through a voltage source using its source sign
    convention, so a consuming circuit commonly yields a negative ``I(VDD)``.
    The absolute product provides a positive consumed-power magnitude.
    """
    if (
        isinstance(supply_voltage_v, bool)
        or isinstance(supply_current_a, bool)
        or not isinstance(supply_voltage_v, (int, float))
        or not isinstance(supply_current_a, (int, float))
        or not isfinite(float(supply_voltage_v))
        or not isfinite(float(supply_current_a))
    ):
        raise ValueError("supply voltage and current must be finite numbers")
    return abs(float(supply_voltage_v) * float(supply_current_a))
