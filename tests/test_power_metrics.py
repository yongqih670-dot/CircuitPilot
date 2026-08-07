from math import isfinite

import pytest

from circuitpilot.circuit_config import CircuitType
from circuitpilot.power_metrics import dc_supply_power, derived_rc_power


def test_dc_supply_power_uses_ngspice_voltage_source_sign_convention() -> None:
    assert dc_supply_power(5.0, -0.005) == pytest.approx(0.025)
    assert dc_supply_power(-1.8, 0.002) == pytest.approx(0.0036)


@pytest.mark.parametrize(
    ("voltage", "current"),
    [(float("nan"), 1.0), (1.0, float("inf")), (True, 1.0)],
)
def test_dc_supply_power_rejects_invalid_inputs(voltage: float, current: float) -> None:
    with pytest.raises(ValueError, match="finite numbers"):
        dc_supply_power(voltage, current)


def test_derived_rc_power_keeps_existing_highpass_result() -> None:
    result = derived_rc_power(
        gain_db=0.0,
        phase_deg=0.0,
        resistance_ohm=1_000.0,
        circuit_type=CircuitType.RC_HIGHPASS,
    )
    assert isfinite(result)
    assert result == pytest.approx(0.0005)


def test_derived_rc_power_rejects_non_rc_template() -> None:
    with pytest.raises(ValueError, match="supports only RC"):
        derived_rc_power(
            gain_db=0.0,
            phase_deg=0.0,
            resistance_ohm=1_000.0,
            circuit_type=CircuitType.VOLTAGE_DIVIDER,
        )
