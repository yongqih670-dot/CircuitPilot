import csv
import json
from math import isfinite, log10, pi
from pathlib import Path
import re

import pytest

from circuitpilot.analysis import (
    find_cutoff_frequency,
    find_highpass_cutoff_frequency,
)
from circuitpilot.circuit_config import (
    CircuitType,
    RCHighPassConfig,
    RCLowPassConfig,
    VoltageDividerConfig,
    load_circuit_config,
)
from circuitpilot.circuit_optimizer import evaluate_response_metric
from circuitpilot.cli import main
from circuitpilot.exceptions import ParseError, SimulationError
from circuitpilot.experiment_manager import ExperimentRepository
from circuitpilot.optimization_config import (
    ObjectiveConfig,
    ObjectiveGoal,
    ObjectiveMetric,
    OptimizationConfig,
    ParameterBounds,
)
from circuitpilot.parser import parse_ac_output
from circuitpilot.simulator import resolve_ngspice_executable, run_ngspice


NGSPICE_EXECUTABLE = resolve_ngspice_executable("ngspice")
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
@pytest.mark.skipif(
    NGSPICE_EXECUTABLE is None,
    reason="a local ngspice executable is required for real-template verification",
)
@pytest.mark.parametrize(
    "example_name",
    ("lowpass.yaml", "highpass.yaml", "voltage_divider.yaml"),
)
def test_every_circuit_template_uses_real_ngspice_output(
    tmp_path: Path, example_name: str
) -> None:
    """Run every stage-two template through the real single-run CLI."""
    config_path = PROJECT_ROOT / "examples" / example_name
    config = load_circuit_config(config_path)
    output = tmp_path / config.circuit_type.value

    status = main(
        [
            "--config",
            str(config_path),
            "--output-dir",
            str(output),
            "--ngspice",
            NGSPICE_EXECUTABLE or "ngspice",
        ]
    )

    assert status == 0
    response = parse_ac_output(output / "ac_results.dat")
    manifest = json.loads(
        (output / "research_manifest.json").read_text(encoding="utf-8")
    )
    assert len(response) > 50
    assert (output / "bode.png").stat().st_size > 0
    assert (output / "input_config.yaml").read_bytes() == config_path.read_bytes()
    assert manifest["reproducibility"]["metric_source"] == "parsed_ngspice_output"

    if isinstance(config.circuit, RCLowPassConfig):
        measured = find_cutoff_frequency(response.frequency_hz, response.gain_db)
        expected = 1.0 / (
            2.0
            * pi
            * config.circuit.resistance_ohm
            * config.circuit.capacitance_f
        )
        assert measured == pytest.approx(expected, rel=0.02)

        gain_config = OptimizationConfig(
            circuit_type=CircuitType.RC_LOWPASS,
            resistance=ParameterBounds(900.0, 1100.0),
            capacitance=ParameterBounds(140e-9, 180e-9),
            objective=ObjectiveConfig(
                metric=ObjectiveMetric.GAIN,
                goal=ObjectiveGoal.MAXIMIZE,
                evaluation_frequency_hz=1000.0,
            ),
            analysis=config.analysis,
        )
        power_config = OptimizationConfig(
            circuit_type=CircuitType.RC_LOWPASS,
            resistance=gain_config.resistance,
            capacitance=gain_config.capacitance,
            objective=ObjectiveConfig(
                metric=ObjectiveMetric.POWER,
                goal=ObjectiveGoal.MINIMIZE,
                evaluation_frequency_hz=1000.0,
            ),
            analysis=config.analysis,
        )
        gain = evaluate_response_metric(
            gain_config,
            response,
            resistance_ohm=config.circuit.resistance_ohm,
        )
        power = evaluate_response_metric(
            power_config,
            response,
            resistance_ohm=config.circuit.resistance_ohm,
        )
        assert isfinite(gain)
        assert isfinite(power) and power > 0
    elif isinstance(config.circuit, RCHighPassConfig):
        measured = find_highpass_cutoff_frequency(
            response.frequency_hz, response.gain_db
        )
        expected = 1.0 / (
            2.0
            * pi
            * config.circuit.resistance_ohm
            * config.circuit.capacitance_f
        )
        assert measured == pytest.approx(expected, rel=0.02)
    else:
        assert isinstance(config.circuit, VoltageDividerConfig)
        expected_gain = 20.0 * log10(
            config.circuit.resistance_bottom_ohm
            / (
                config.circuit.resistance_top_ohm
                + config.circuit.resistance_bottom_ohm
            )
        )
        assert max(response.gain_db) - min(response.gain_db) < 1e-9
        assert response.gain_db[0] == pytest.approx(expected_gain, abs=1e-6)


@pytest.mark.integration
@pytest.mark.skipif(
    NGSPICE_EXECUTABLE is None,
    reason="a local ngspice executable is required for the research-readiness E2E test",
)
def test_config_to_real_optimization_to_database_and_manifest(
    tmp_path: Path,
) -> None:
    """Exercise the complete research path without monkeypatch or synthetic data."""
    config_path = tmp_path / "optimization.yaml"
    config_path.write_text(
        """circuit:
  type: rc_lowpass
objective:
  metric: bandwidth
  goal: target
  target_value: 1000
parameters:
  R: {min: 900, max: 1100, scale: log}
  C: {min: 140e-9, max: 180e-9, scale: log}
optimizer:
  max_iterations: 1
  population_size: 2
  tolerance: 0.01
  seed: 17
  polish: false
analysis:
  start_frequency_hz: 10
  stop_frequency_hz: 100000
  points_per_decade: 50
""",
        encoding="utf-8",
    )
    output = tmp_path / "research_run"
    database = tmp_path / "experiments.sqlite3"

    status = main(
        [
            "--optimize-config",
            str(config_path),
            "--output-dir",
            str(output),
            "--ngspice",
            NGSPICE_EXECUTABLE or "ngspice",
            "--experiment-name",
            "research readiness real E2E",
            "--experiment-database",
            str(database),
        ]
    )

    assert status == 0
    manifest = json.loads(
        (output / "research_manifest.json").read_text(encoding="utf-8")
    )
    summary = json.loads(
        (output / "optimization_summary.json").read_text(encoding="utf-8")
    )
    record = ExperimentRepository(database).list_experiments()[0]
    best = summary["best"]
    best_directory = output / best["run_directory"]
    netlist_path = best_directory / "rc_lowpass.cir"
    data_path = best_directory / "ac_results.dat"
    log_path = best_directory / "ngspice.log"

    assert manifest["status"] == "success"
    assert manifest["reproducibility"]["random_seed"] == 17
    assert manifest["reproducibility"]["metric_source"] == "parsed_ngspice_output"
    assert manifest["timing"]["runtime_seconds"] > 0
    assert manifest["experiment"]["database_id"] == record.experiment_id
    assert (output / "input_config.yaml").read_bytes() == config_path.read_bytes()
    assert netlist_path.is_file()
    assert data_path.is_file()
    assert log_path.is_file()
    assert "ngspice" in log_path.read_text(encoding="utf-8", errors="replace").lower()

    response = parse_ac_output(data_path)
    measured_cutoff = find_cutoff_frequency(response.frequency_hz, response.gain_db)
    assert len(response) > 100
    assert measured_cutoff == pytest.approx(best["metric_value"], rel=1e-9)
    assert record.metrics["bandwidth_hz"] == pytest.approx(measured_cutoff, rel=1e-9)
    assert manifest["metrics"]["bandwidth_hz"] == pytest.approx(
        measured_cutoff, rel=1e-9
    )

    netlist = netlist_path.read_text(encoding="utf-8")
    resistance = float(re.search(r"R1 in out ([0-9.e+-]+)", netlist).group(1))  # type: ignore[union-attr]
    capacitance = float(re.search(r"C1 out 0 ([0-9.e+-]+)", netlist).group(1))  # type: ignore[union-attr]
    theoretical_cutoff = 1.0 / (2.0 * pi * resistance * capacitance)
    assert resistance == pytest.approx(best["resistance_ohm"], rel=1e-11)
    assert capacitance == pytest.approx(best["capacitance_f"], rel=1e-11)
    assert measured_cutoff == pytest.approx(theoretical_cutoff, rel=0.02)

    with (output / "optimization_history.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert rows
    assert all(row["status"] == "success" for row in rows)
    assert all(row["metric_value"] for row in rows)
    artifact_categories = {item["category"] for item in manifest["artifacts"]}
    assert {"configuration", "netlist", "ngspice_log", "ngspice_output"} <= (
        artifact_categories
    )


def test_missing_ngspice_and_unparseable_output_never_return_defaults(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "missing_ngspice"

    status = main(
        [
            "--output-dir",
            str(output),
            "--ngspice",
            str(tmp_path / "definitely_missing_ngspice"),
        ]
    )

    assert status == 1
    assert "was not found" in capsys.readouterr().err
    assert not (output / "ac_results.dat").exists()
    assert not (output / "research_manifest.json").exists()

    invalid_output = tmp_path / "invalid_ac_results.dat"
    invalid_output.write_text("not numeric simulation output\n", encoding="utf-8")
    with pytest.raises(ParseError, match="contains no data rows"):
        parse_ac_output(invalid_output)


@pytest.mark.integration
@pytest.mark.skipif(
    NGSPICE_EXECUTABLE is None,
    reason="a local ngspice executable is required for failure propagation",
)
def test_real_ngspice_nonzero_exit_is_an_error(tmp_path: Path) -> None:
    invalid_netlist = tmp_path / "invalid.cir"
    invalid_netlist.write_text(
        "* deliberately invalid research audit netlist\n"
        "R1 in out definitely_not_a_value\n"
        ".ac dec 10 1 1000\n"
        ".end\n",
        encoding="utf-8",
    )

    with pytest.raises(SimulationError, match="exited with status"):
        run_ngspice(
            invalid_netlist,
            executable=NGSPICE_EXECUTABLE or "ngspice",
            log_path=tmp_path / "ngspice.log",
        )
