from math import pi
from pathlib import Path

import pytest

from circuitpilot.circuit_config import CircuitType
from circuitpilot.exceptions import ConfigError
from circuitpilot.sweep_config import (
    generate_parameter_combinations,
    load_sweep_config,
)


def test_load_sweep_config_expands_user_example_and_derives_analysis(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sweep.yaml"
    source.write_text(
        """target:
  cutoff_frequency: 10000
parameters:
  R:
    min: 100
    max: 300
    step: 100
  C:
    values:
      - 1e-9
      - 10e-9
      - 100e-9
""",
        encoding="utf-8",
    )

    config = load_sweep_config(source)
    combinations = generate_parameter_combinations(config)

    assert config.circuit_type is CircuitType.RC_LOWPASS
    assert config.resistance_values_ohm == (100.0, 200.0, 300.0)
    assert config.capacitance_values_f == (1e-9, 10e-9, 100e-9)
    assert config.combination_count == 9
    assert combinations[0].resistance_ohm == 100.0
    assert combinations[0].capacitance_f == pytest.approx(1e-9)
    assert combinations[-1].resistance_ohm == 300.0
    assert combinations[-1].capacitance_f == pytest.approx(100e-9)
    minimum_cutoff = 1.0 / (2.0 * pi * 300.0 * 100e-9)
    maximum_cutoff = 1.0 / (2.0 * pi * 100.0 * 1e-9)
    assert config.analysis.start_frequency_hz < minimum_cutoff
    assert config.analysis.stop_frequency_hz > maximum_cutoff


def test_load_sweep_config_accepts_highpass_and_explicit_analysis(
    tmp_path: Path,
) -> None:
    source = tmp_path / "highpass_sweep.yaml"
    source.write_text(
        """circuit:
  type: rc_highpass
target:
  cutoff_frequency_hz: 5000
parameters:
  R:
    values: [1000, 2000]
  C:
    min: 1e-9
    max: 3e-9
    step: 1e-9
analysis:
  start_frequency_hz: 10
  stop_frequency_hz: 10000000
  points_per_decade: 50
top_n: 2
""",
        encoding="utf-8",
    )

    config = load_sweep_config(source)

    assert config.circuit_type is CircuitType.RC_HIGHPASS
    assert config.capacitance_values_f == (1e-9, 2e-9, 3e-9)
    assert config.analysis.points_per_decade == 50
    assert config.top_n == 2


@pytest.mark.parametrize(
    "contents, message",
    [
        (
            "target: {cutoff_frequency: 1000}\nparameters: {R: {values: []}, C: {values: [1e-9]}}\n",
            "non-empty YAML list",
        ),
        (
            "target: {cutoff_frequency: 1000}\nparameters: {R: {min: 10, max: 1, step: 1}, C: {values: [1e-9]}}\n",
            "max must be greater",
        ),
        (
            "target: {cutoff_frequency: 0}\nparameters: {R: {values: [100]}, C: {values: [1e-9]}}\n",
            "finite positive",
        ),
        (
            "circuit: voltage_divider\ntarget: {cutoff_frequency: 1000}\nparameters: {R: {values: [100]}, C: {values: [1e-9]}}\n",
            "has no cutoff",
        ),
        (
            "target: {cutoff_frequency: 1000}\nparameters: {R: {values: [100, 100]}, C: {values: [1e-9]}}\n",
            "must not contain duplicates",
        ),
    ],
)
def test_load_sweep_config_rejects_invalid_parameter_spaces(
    tmp_path: Path, contents: str, message: str
) -> None:
    source = tmp_path / "invalid.yaml"
    source.write_text(contents, encoding="utf-8")

    with pytest.raises(ConfigError, match=message):
        load_sweep_config(source)


def test_load_sweep_config_wraps_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="failed to read sweep configuration"):
        load_sweep_config(tmp_path / "missing.yaml")


def test_bundled_sweep_example_is_valid() -> None:
    config = load_sweep_config(Path("examples") / "sweep_lowpass.yaml")

    assert config.target_cutoff_frequency_hz == pytest.approx(10_000.0)
    assert config.combination_count == 300
    assert config.top_n == 10
