from math import pi
from pathlib import Path

import pytest

from circuitpilot.analysis import find_cutoff_frequency
from circuitpilot.netlist import RCFilterConfig, write_rc_lowpass_netlist
from circuitpilot.parameter_sweep import run_parameter_sweep
from circuitpilot.parser import parse_ac_output
from circuitpilot.simulator import resolve_ngspice_executable, run_ngspice
from circuitpilot.sweep_config import SweepConfig
from circuitpilot.circuit_config import ACAnalysisConfig, CircuitType


NGSPICE_EXECUTABLE = resolve_ngspice_executable("ngspice")


@pytest.mark.integration
@pytest.mark.skipif(
    NGSPICE_EXECUTABLE is None,
    reason="a local ngspice executable is required for this integration test",
)
def test_real_ngspice_rc_lowpass_end_to_end(tmp_path: Path) -> None:
    config = RCFilterConfig(
        resistance_ohm=1_000.0,
        capacitance_f=159.154943e-9,
        start_frequency_hz=10.0,
        stop_frequency_hz=100_000.0,
        points_per_decade=100,
    )
    netlist_path = tmp_path / "rc_lowpass.cir"
    data_path = tmp_path / "ac_results.dat"

    write_rc_lowpass_netlist(netlist_path, data_path, config)
    run_ngspice(
        netlist_path,
        executable=NGSPICE_EXECUTABLE or "ngspice",
        log_path=tmp_path / "ngspice.log",
    )
    response = parse_ac_output(data_path)
    cutoff_hz = find_cutoff_frequency(response.frequency_hz, response.gain_db)
    theoretical_hz = 1.0 / (2.0 * pi * config.resistance_ohm * config.capacitance_f)

    assert len(response) > 100
    assert cutoff_hz == pytest.approx(theoretical_hz, rel=0.02)


@pytest.mark.integration
@pytest.mark.skipif(
    NGSPICE_EXECUTABLE is None,
    reason="a local ngspice executable is required for this integration test",
)
def test_real_ngspice_two_point_parameter_sweep(tmp_path: Path) -> None:
    config = SweepConfig(
        target_cutoff_frequency_hz=1_000.0,
        resistance_values_ohm=(1_000.0, 2_000.0),
        capacitance_values_f=(159.154943e-9,),
        analysis=ACAnalysisConfig(10.0, 100_000.0, 100),
        circuit_type=CircuitType.RC_LOWPASS,
        top_n=2,
    )

    results = run_parameter_sweep(
        config,
        tmp_path,
        executable=NGSPICE_EXECUTABLE or "ngspice",
    )

    assert len(results) == 2
    assert all(result.succeeded for result in results)
    assert results[0].simulated_cutoff_frequency_hz == pytest.approx(1_000.0, rel=0.02)
    assert results[0].relative_error < results[1].relative_error  # type: ignore[operator]
