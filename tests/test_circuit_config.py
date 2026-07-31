from pathlib import Path

import pytest

from circuitpilot.circuit_config import (
    CircuitType,
    RCHighPassConfig,
    RCLowPassConfig,
    VoltageDividerConfig,
    load_circuit_config,
)
from circuitpilot.exceptions import ConfigError


@pytest.mark.parametrize(
    "circuit_type, parameters, expected_class",
    [
        (
            "rc_lowpass",
            "resistance_ohm: 2200\n    capacitance_f: 4.7e-8",
            RCLowPassConfig,
        ),
        (
            "rc_highpass",
            "resistance_ohm: 10000\n    capacitance_f: 1.0e-9",
            RCHighPassConfig,
        ),
        (
            "voltage_divider",
            "resistance_top_ohm: 10000\n    resistance_bottom_ohm: 3300",
            VoltageDividerConfig,
        ),
    ],
)
def test_load_circuit_config_converts_each_template_to_python_objects(
    tmp_path: Path,
    circuit_type: str,
    parameters: str,
    expected_class: type,
) -> None:
    source = tmp_path / "circuit.yaml"
    source.write_text(
        f"""circuit:
  type: {circuit_type}
  parameters:
    {parameters}
analysis:
  start_frequency_hz: 10
  stop_frequency_hz: 1000000
  points_per_decade: 50
""",
        encoding="utf-8",
    )

    config = load_circuit_config(source)

    assert isinstance(config.circuit, expected_class)
    assert config.circuit_type is CircuitType(circuit_type)
    assert config.analysis.points_per_decade == 50


@pytest.mark.parametrize(
    "contents, message",
    [
        (
            "circuit:\n  type: unknown\n  parameters: {}\nanalysis: {}\n",
            "unsupported circuit.type",
        ),
        (
            """circuit:
  type: rc_lowpass
  parameters:
    resistance_ohm: -1
    capacitance_f: 1.0e-9
analysis:
  start_frequency_hz: 10
  stop_frequency_hz: 1000
  points_per_decade: 10
""",
            "resistance_ohm must be a finite positive number",
        ),
        (
            """circuit:
  type: voltage_divider
  parameters:
    resistance_top_ohm: 1000
analysis:
  start_frequency_hz: 10
  stop_frequency_hz: 1000
  points_per_decade: 10
""",
            "missing required field",
        ),
        (
            """circuit:
  type: rc_highpass
  parameters:
    resistance_ohm: 1000
    capacitance_f: 1.0e-9
    typo: 1
analysis:
  start_frequency_hz: 10
  stop_frequency_hz: 1000
  points_per_decade: 10
""",
            "unknown field",
        ),
        (
            """circuit:
  type: rc_lowpass
  parameters:
    resistance_ohm: 1000
    capacitance_f: 1.0e-9
analysis:
  start_frequency_hz: 1000
  stop_frequency_hz: 10
  points_per_decade: 10
""",
            "stop_frequency_hz must be greater",
        ),
    ],
)
def test_load_circuit_config_rejects_invalid_values(
    tmp_path: Path, contents: str, message: str
) -> None:
    source = tmp_path / "invalid.yaml"
    source.write_text(contents, encoding="utf-8")

    with pytest.raises(ConfigError, match=message):
        load_circuit_config(source)


def test_load_circuit_config_rejects_malformed_yaml(tmp_path: Path) -> None:
    source = tmp_path / "broken.yaml"
    source.write_text("circuit: [unterminated", encoding="utf-8")

    with pytest.raises(ConfigError, match="invalid YAML"):
        load_circuit_config(source)


def test_load_circuit_config_wraps_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="failed to read configuration"):
        load_circuit_config(tmp_path / "missing.yaml")


@pytest.mark.parametrize(
    "filename, expected_type",
    [
        ("lowpass.yaml", CircuitType.RC_LOWPASS),
        ("highpass.yaml", CircuitType.RC_HIGHPASS),
        ("voltage_divider.yaml", CircuitType.VOLTAGE_DIVIDER),
    ],
)
def test_bundled_example_configs_are_valid(
    filename: str, expected_type: CircuitType
) -> None:
    config = load_circuit_config(Path("examples") / filename)

    assert config.circuit_type is expected_type
