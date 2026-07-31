from math import log10
from pathlib import Path

import pytest

from circuitpilot.circuit_config import CircuitType
from circuitpilot.exceptions import ConfigError
from circuitpilot.optimization_config import (
    ObjectiveGoal,
    ObjectiveMetric,
    ParameterScale,
    load_optimization_config,
)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "optimization.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_load_bandwidth_target_with_derived_analysis(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """circuit:
  type: rc_lowpass
objective:
  metric: bandwidth
  goal: target
  target_value: 10000
parameters:
  R:
    min: 100
    max: 10000
    scale: log
  C:
    min: 1e-9
    max: 100e-9
optimizer:
  max_iterations: 4
  population_size: 5
  seed: 7
  tolerance: 0.0001
  polish: false
""",
    )

    config = load_optimization_config(path)

    assert config.circuit_type is CircuitType.RC_LOWPASS
    assert config.objective.metric is ObjectiveMetric.BANDWIDTH
    assert config.objective.goal is ObjectiveGoal.TARGET
    assert config.objective.target_value == 10_000.0
    assert config.resistance.optimizer_bounds == pytest.approx((2.0, 4.0))
    assert config.decode_parameters((3.0, -8.0)) == pytest.approx((1000.0, 1e-8))
    assert config.analysis.start_frequency_hz < 10_000.0
    assert config.analysis.stop_frequency_hz > 10_000.0
    assert config.optimizer.seed == 7
    assert not config.optimizer.polish


@pytest.mark.parametrize(
    ("metric", "goal"),
    [("gain", "maximize"), ("power", "minimize")],
)
def test_load_frequency_specific_objectives(
    tmp_path: Path, metric: str, goal: str
) -> None:
    path = _write(
        tmp_path,
        f"""circuit:
  type: rc_highpass
objective:
  metric: {metric}
  goal: {goal}
  evaluation_frequency_hz: 1000
parameters:
  R: {{min: 100, max: 1000, scale: linear}}
  C: {{min: 1e-9, max: 1e-7}}
analysis:
  start_frequency_hz: 10
  stop_frequency_hz: 100000
  points_per_decade: 50
""",
    )

    config = load_optimization_config(path)

    assert config.objective.metric.value == metric
    assert config.objective.goal.value == goal
    assert config.objective.evaluation_frequency_hz == 1_000.0
    assert config.resistance.scale is ParameterScale.LINEAR
    assert config.resistance.optimizer_bounds == (100.0, 1_000.0)
    assert config.capacitance.optimizer_bounds == pytest.approx((-9.0, -7.0))
    assert log10(config.capacitance.decode(-8.0)) == pytest.approx(-8.0)


@pytest.mark.parametrize(
    ("objective", "message"),
    [
        ("metric: gain\n  goal: minimize\n  evaluation_frequency_hz: 1000", "requires goal 'maximize'"),
        ("metric: power\n  goal: minimize", "requires objective.evaluation_frequency_hz"),
        ("metric: bandwidth\n  goal: target", "requires objective.target_value"),
    ],
)
def test_rejects_invalid_objective_combinations(
    tmp_path: Path, objective: str, message: str
) -> None:
    path = _write(
        tmp_path,
        f"""circuit:
  type: rc_lowpass
objective:
  {objective}
parameters:
  R: {{min: 100, max: 1000}}
  C: {{min: 1e-9, max: 1e-7}}
""",
    )

    with pytest.raises(ConfigError, match=message):
        load_optimization_config(path)


def test_rejects_reversed_bounds_and_unknown_fields(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """circuit:
  type: rc_lowpass
objective:
  metric: bandwidth
  goal: target
  target_value: 1000
parameters:
  R: {min: 1000, max: 100}
  C: {min: 1e-9, max: 1e-7}
surprise: true
""",
    )

    with pytest.raises(ConfigError, match="unknown field.*surprise"):
        load_optimization_config(path)
