from pathlib import Path

import pytest

from circuitpilot.circuit_config import (
    ACAnalysisConfig,
    CircuitConfig,
    RCHighPassConfig,
    RCLowPassConfig,
    VoltageDividerConfig,
)
from circuitpilot.netlist_generator import generate_netlist, write_netlist


def _analysis() -> ACAnalysisConfig:
    return ACAnalysisConfig(
        start_frequency_hz=20,
        stop_frequency_hz=2_000_000,
        points_per_decade=80,
    )


@pytest.mark.parametrize(
    "circuit, expected_lines",
    [
        (
            RCLowPassConfig(resistance_ohm=2_200, capacitance_f=47e-9),
            ("R1 in out 2200", "C1 out 0 4.7e-08"),
        ),
        (
            RCHighPassConfig(resistance_ohm=10_000, capacitance_f=1e-9),
            ("C1 in out 1e-09", "R1 out 0 10000"),
        ),
        (
            VoltageDividerConfig(
                resistance_top_ohm=12_000, resistance_bottom_ohm=3_300
            ),
            ("R1 in out 12000", "R2 out 0 3300"),
        ),
    ],
)
def test_generate_netlist_uses_template_and_parameter_values(
    tmp_path: Path, circuit: object, expected_lines: tuple[str, str]
) -> None:
    config = CircuitConfig(circuit=circuit, analysis=_analysis())  # type: ignore[arg-type]

    netlist = generate_netlist(config, tmp_path / "ac.dat")

    assert expected_lines[0] in netlist
    assert expected_lines[1] in netlist
    assert "ac dec 80 20 2000000" in netlist
    assert "vdb(out) vp(out)" in netlist
    assert netlist.endswith(".end\n")


def test_write_netlist_creates_destination_directories(tmp_path: Path) -> None:
    config = CircuitConfig(
        circuit=VoltageDividerConfig(1_000, 1_000),
        analysis=_analysis(),
    )
    netlist_path = tmp_path / "netlists" / "divider.cir"
    data_path = tmp_path / "results" / "divider.dat"

    written = write_netlist(netlist_path, data_path, config)

    assert written == netlist_path.resolve()
    assert written.is_file()
    assert data_path.parent.is_dir()

