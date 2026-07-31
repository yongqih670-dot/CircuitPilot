from pathlib import Path

import pytest

from circuitpilot.cli import main
from circuitpilot.experiment_manager import ExperimentRepository
from circuitpilot.parameter_sweep import SweepResult
from circuitpilot.parser import ACAnalysisResult
from circuitpilot.simulator import SimulationResult


def _create_with_cli(
    database: Path,
    *,
    name: str,
    relative_error: float,
    cutoff_hz: float,
) -> int:
    return main(
        [
            "experiment",
            "create",
            "--name",
            name,
            "--circuit-type",
            "rc_lowpass",
            "--parameters",
            '{"R": 1000, "C": 1.59e-7}',
            "--simulation-time",
            "0.05",
            "--metrics",
            f'{{"relative_error": {relative_error}, "cutoff_frequency_hz": {cutoff_hz}}}',
            "--database",
            str(database),
        ]
    )


def test_experiment_cli_create_list_best_and_compare(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "experiments.sqlite3"
    assert _create_with_cli(
        database, name="baseline", relative_error=0.1, cutoff_hz=900.0
    ) == 0
    assert _create_with_cli(
        database, name="improved", relative_error=0.01, cutoff_hz=990.0
    ) == 0
    capsys.readouterr()

    list_status = main(["experiment", "list", "--database", str(database)])
    list_output = capsys.readouterr().out
    best_status = main(
        [
            "experiment",
            "best",
            "--metric",
            "relative_error",
            "--database",
            str(database),
        ]
    )
    best_output = capsys.readouterr().out
    compare_status = main(
        [
            "experiment",
            "compare",
            "--metric",
            "cutoff_frequency_hz",
            "--ids",
            "1",
            "2",
            "--database",
            str(database),
        ]
    )
    compare_output = capsys.readouterr().out

    assert list_status == best_status == compare_status == 0
    assert "Experiments: 2" in list_output
    assert "baseline" in list_output and "improved" in list_output
    assert "Best result" in best_output and "improved" in best_output
    assert "History comparison" in compare_output
    assert "0.1" in compare_output


def test_single_simulation_can_be_saved_automatically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = ACAnalysisResult(
        frequency_hz=(10.0, 100.0, 1_000.0),
        gain_db=(0.0, -3.0, -20.0),
        phase_deg=(-1.0, -45.0, -85.0),
    )
    simulation = SimulationResult(
        command=("ngspice",),
        returncode=0,
        stdout="",
        stderr="",
        elapsed_seconds=0.125,
    )
    monkeypatch.setattr(
        "circuitpilot.cli.run_ngspice", lambda *args, **kwargs: simulation
    )
    monkeypatch.setattr("circuitpilot.cli.parse_ac_output", lambda path: response)
    monkeypatch.setattr(
        "circuitpilot.cli.plot_bode", lambda result, path, **kwargs: Path(path)
    )
    database = tmp_path / "experiments.sqlite3"

    status = main(
        [
            "--output-dir",
            str(tmp_path / "output"),
            "--experiment-name",
            "saved lowpass",
            "--experiment-database",
            str(database),
        ]
    )

    record = ExperimentRepository(database).list_experiments()[0]
    assert status == 0
    assert record.name == "saved lowpass"
    assert record.simulation_time_seconds == pytest.approx(0.125)
    assert record.metrics["cutoff_frequency_hz"] == pytest.approx(100.0)
    assert record.parameters["circuit"]["resistance_ohm"] == pytest.approx(1_000.0)


def test_parameter_sweep_can_be_saved_as_summary_experiment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "sweep.yaml"
    config_path.write_text(
        """target:
  cutoff_frequency: 10000
parameters:
  R:
    values: [1000, 2000]
  C:
    values: [1e-8]
""",
        encoding="utf-8",
    )
    results = (
        SweepResult(1, 1000.0, 1e-8, 10000.0, 12000.0, 0.2, "success"),
        SweepResult(2, 2000.0, 1e-8, 10000.0, 10100.0, 0.01, "success"),
    )
    monkeypatch.setattr(
        "circuitpilot.cli.run_parameter_sweep",
        lambda config, output_dir, **kwargs: results,
    )
    database = tmp_path / "experiments.sqlite3"

    status = main(
        [
            "--sweep-config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "output"),
            "--experiment-name",
            "saved sweep",
            "--experiment-database",
            str(database),
        ]
    )

    record = ExperimentRepository(database).list_experiments()[0]
    assert status == 0
    assert record.name == "saved sweep"
    assert record.metrics["best_relative_error"] == pytest.approx(0.01)
    assert record.metrics["combination_count"] == pytest.approx(2.0)

