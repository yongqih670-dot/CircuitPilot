from pathlib import Path

import pytest

from circuitpilot.exceptions import ConfigError
from circuitpilot.experiments.config import (
    ObjectiveType,
    load_experiment_config,
)


VALID_CONFIG = """experiment:
  name: rc_baseline_test
  circuit: rc_lowpass
  method: random
  seed: 0
  simulation_budget: 50
  output_dir: research_runs
  resume: false
  timeout: 30
search_space:
  resistance:
    type: float
    low: 100
    high: 10000
    log: true
  capacitance:
    type: float
    low: 1e-9
    high: 1e-6
    log: true
objectives:
  bandwidth:
    type: target
    target: 10000
constraints: {}
optimizer_config: {}
ngspice_config:
  executable: ngspice
  start_frequency_hz: 10
  stop_frequency_hz: 10000000
  points_per_decade: 50
"""


def test_loads_common_experiment_yaml(tmp_path: Path) -> None:
    source = tmp_path / "experiment.yaml"
    source.write_text(VALID_CONFIG, encoding="utf-8")

    config = load_experiment_config(source)

    assert config.experiment_name == "rc_baseline_test"
    assert config.circuit_name == "rc_lowpass"
    assert config.method == "random"
    assert config.seed == 0
    assert config.simulation_budget == 50
    assert config.objectives[0].objective_type is ObjectiveType.TARGET
    assert config.objectives[0].target == 10_000.0
    assert set(config.search_space_by_name) == {"resistance", "capacitance"}
    assert len(config.identity_sha256()) == 64


@pytest.mark.parametrize(
    ("old", "new", "message"),
    (
        ("simulation_budget: 50", "simulation_budget: 0", "positive integer"),
        ("low: 100", "low: -100", "positive for log sampling"),
        ("method: random", "method: random\n  extra: invalid", "unknown field"),
    ),
)
def test_rejects_invalid_experiment_yaml(
    tmp_path: Path, old: str, new: str, message: str
) -> None:
    source = tmp_path / "invalid.yaml"
    source.write_text(VALID_CONFIG.replace(old, new, 1), encoding="utf-8")

    with pytest.raises(ConfigError, match=message):
        load_experiment_config(source)


def test_optimizer_config_cannot_define_an_independent_seed(tmp_path: Path) -> None:
    source = tmp_path / "seed.yaml"
    source.write_text(
        VALID_CONFIG.replace("optimizer_config: {}", "optimizer_config:\n  seed: 99"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="only seed entry"):
        load_experiment_config(source)
