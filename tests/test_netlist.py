from pathlib import Path

import pytest

from circuitpilot.netlist import (
    RCFilterConfig,
    generate_rc_lowpass_netlist,
    write_rc_lowpass_netlist,
)


def test_generate_rc_lowpass_netlist_contains_circuit_and_ac_sweep(tmp_path: Path) -> None:
    config = RCFilterConfig(
        resistance_ohm=2_200,
        capacitance_f=47e-9,
        start_frequency_hz=20,
        stop_frequency_hz=200_000,
        points_per_decade=50,
    )

    netlist = generate_rc_lowpass_netlist(config, tmp_path / "ac.dat")

    assert "R1 in out 2200" in netlist
    assert "C1 out 0 4.7e-08" in netlist
    assert "ac dec 50 20 200000" in netlist
    assert "wrdata" in netlist
    assert "vdb(out) vp(out)" in netlist
    assert netlist.endswith(".end\n")


@pytest.mark.parametrize(
    "overrides",
    [
        {"resistance_ohm": 0},
        {"capacitance_f": -1e-9},
        {"start_frequency_hz": float("inf")},
        {"start_frequency_hz": 100, "stop_frequency_hz": 100},
        {"points_per_decade": 1},
    ],
)
def test_config_rejects_invalid_values(overrides: dict[str, float | int]) -> None:
    with pytest.raises(ValueError):
        RCFilterConfig(**overrides)


def test_write_rc_lowpass_netlist_creates_parent_directories(tmp_path: Path) -> None:
    netlist_path = tmp_path / "nested" / "filter.cir"
    result_path = tmp_path / "results" / "ac.dat"

    written_path = write_rc_lowpass_netlist(netlist_path, result_path)

    assert written_path == netlist_path.resolve()
    assert written_path.is_file()
    assert result_path.parent.is_dir()

