from pathlib import Path

import pytest

from circuitpilot.cli import main
from circuitpilot.circuit_optimizer import OptimizationEvaluation, OptimizationResult
from circuitpilot.exceptions import SimulationError
from circuitpilot.experiment_manager import ExperimentRepository
from circuitpilot.parameter_sweep import SweepResult
from circuitpilot.parser import ACAnalysisResult
from circuitpilot.simulator import SimulationResult


@pytest.fixture(autouse=True)
def isolate_research_manifest_in_cli_unit_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep CLI unit tests focused; real manifests are covered end to end."""
    monkeypatch.setattr(
        "circuitpilot.cli.write_research_manifest",
        lambda output_directory, **kwargs: Path(output_directory)
        / "research_manifest.json",
    )


def _successful_simulation() -> SimulationResult:
    return SimulationResult(("ngspice",), 0, "", "", 0.01)


def _patch_successful_single_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch only the physical boundary for CLI directory-lifecycle tests."""
    response = ACAnalysisResult(
        frequency_hz=(10.0, 100.0, 1_000.0),
        gain_db=(0.0, -3.0, -20.0),
        phase_deg=(-1.0, -45.0, -85.0),
    )
    monkeypatch.setattr(
        "circuitpilot.cli.run_ngspice", lambda *args, **kwargs: _successful_simulation()
    )
    monkeypatch.setattr("circuitpilot.cli.parse_ac_output", lambda path: response)
    monkeypatch.setattr(
        "circuitpilot.cli.plot_bode", lambda result, path, **kwargs: Path(path)
    )


def test_default_cli_output_creates_unique_run_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    _patch_successful_single_run(monkeypatch)

    status = main([])

    captured = capsys.readouterr()
    runs = list((tmp_path / "output").iterdir())
    assert status == 0
    assert len(runs) == 1
    assert runs[0].name.startswith("cp-")
    assert (runs[0] / "run_context.json").is_file()
    assert f"Run ID: {runs[0].name}" in captured.out
    assert f"Output directory: {runs[0]}" in captured.out


def test_cli_refuses_reuse_without_resume_and_accepts_explicit_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _patch_successful_single_run(monkeypatch)
    output = tmp_path / "run"

    assert main(["--output-dir", str(output)]) == 0
    assert main(["--output-dir", str(output)]) == 1
    assert "not empty" in capsys.readouterr().err
    assert (
        main(
            [
                "--output-dir",
                str(output),
                "--resume",
                "--resistance",
                "2000",
            ]
        )
        == 1
    )
    assert "resolved configuration" in capsys.readouterr().err
    assert main(["--output-dir", str(output), "--resume"]) == 0


def test_main_runs_complete_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    response = ACAnalysisResult(
        frequency_hz=(10.0, 100.0, 1_000.0),
        gain_db=(0.0, -3.0, -20.0),
        phase_deg=(-1.0, -45.0, -85.0),
    )
    monkeypatch.setattr(
        "circuitpilot.cli.run_ngspice", lambda *args, **kwargs: _successful_simulation()
    )
    monkeypatch.setattr("circuitpilot.cli.parse_ac_output", lambda path: response)
    monkeypatch.setattr(
        "circuitpilot.cli.plot_bode", lambda result, path, **kwargs: Path(path)
    )

    status = main(["--output-dir", str(tmp_path)])

    captured = capsys.readouterr()
    assert status == 0
    assert "100 Hz" in captured.out
    assert (tmp_path / "rc_lowpass.cir").is_file()


def test_main_converts_expected_failure_to_status_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise SimulationError("ngspice failed")

    monkeypatch.setattr("circuitpilot.cli.run_ngspice", fail)

    status = main(["--output-dir", str(tmp_path)])

    captured = capsys.readouterr()
    assert status == 1
    assert "ngspice failed" in captured.err


def test_main_loads_highpass_yaml_and_generates_selected_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "highpass.yaml"
    config_path.write_text(
        """circuit:
  type: rc_highpass
  parameters:
    resistance_ohm: 2200
    capacitance_f: 4.7e-8
analysis:
  start_frequency_hz: 10
  stop_frequency_hz: 1000000
  points_per_decade: 50
""",
        encoding="utf-8",
    )
    response = ACAnalysisResult(
        frequency_hz=(10.0, 100.0, 1_000.0),
        gain_db=(-20.0, -3.0, 0.0),
        phase_deg=(85.0, 45.0, 5.0),
    )
    monkeypatch.setattr(
        "circuitpilot.cli.run_ngspice", lambda *args, **kwargs: _successful_simulation()
    )
    monkeypatch.setattr("circuitpilot.cli.parse_ac_output", lambda path: response)
    monkeypatch.setattr(
        "circuitpilot.cli.plot_bode", lambda result, path, **kwargs: Path(path)
    )

    status = main(
        ["--config", str(config_path), "--output-dir", str(tmp_path / "output")]
    )

    captured = capsys.readouterr()
    netlist = (tmp_path / "output" / "rc_highpass.cir").read_text(encoding="utf-8")
    assert status == 0
    assert "Circuit type: rc_highpass" in captured.out
    assert "-3 dB cutoff frequency: 100 Hz" in captured.out
    assert "C1 in out 4.7e-08" in netlist
    assert "R1 out 0 2200" in netlist


def test_main_runs_voltage_divider_without_cutoff_measurement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "divider.yaml"
    config_path.write_text(
        """circuit:
  type: voltage_divider
  parameters:
    resistance_top_ohm: 10000
    resistance_bottom_ohm: 3300
analysis:
  start_frequency_hz: 10
  stop_frequency_hz: 1000
  points_per_decade: 20
""",
        encoding="utf-8",
    )
    response = ACAnalysisResult(
        frequency_hz=(10.0, 100.0, 1_000.0),
        gain_db=(-12.3, -12.3, -12.3),
        phase_deg=(0.0, 0.0, 0.0),
    )
    monkeypatch.setattr(
        "circuitpilot.cli.run_ngspice", lambda *args, **kwargs: _successful_simulation()
    )
    monkeypatch.setattr("circuitpilot.cli.parse_ac_output", lambda path: response)
    monkeypatch.setattr(
        "circuitpilot.cli.plot_bode", lambda result, path, **kwargs: Path(path)
    )

    status = main(
        ["--config", str(config_path), "--output-dir", str(tmp_path / "output")]
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "Circuit type: voltage_divider" in captured.out
    assert "Transfer gain: -12.3 dB" in captured.out
    assert "cutoff frequency" not in captured.out


def test_main_runs_sweep_and_writes_ranked_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
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
top_n: 10
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

    status = main(
        [
            "--sweep-config",
            str(config_path),
            "--output-dir",
            str(tmp_path / "output"),
        ]
    )

    captured = capsys.readouterr()
    assert status == 0
    assert "Top 10 solutions" in captured.out
    assert "2 succeeded, 0 failed" in captured.out
    assert (tmp_path / "output" / "sweep_results.csv").is_file()
    assert (tmp_path / "output" / "parameter_performance.png").is_file()


def test_main_runs_optimization_exports_artifacts_and_saves_experiment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config_path = tmp_path / "optimize.yaml"
    config_path.write_text(
        """circuit:
  type: rc_lowpass
objective:
  metric: bandwidth
  goal: target
  target_value: 10000
parameters:
  R: {min: 500, max: 5000}
  C: {min: 1e-9, max: 100e-9}
optimizer:
  max_iterations: 2
  population_size: 3
  polish: false
""",
        encoding="utf-8",
    )
    best = OptimizationEvaluation(
        evaluation_index=2,
        resistance_ohm=1_590.0,
        capacitance_f=10e-9,
        metric_value=10_007.0,
        objective_value=0.0007,
        status="success",
        simulation_time_seconds=0.02,
        run_directory=str(tmp_path / "output" / "runs" / "evaluation_00002"),
    )
    first = OptimizationEvaluation(
        evaluation_index=1,
        resistance_ohm=1_000.0,
        capacitance_f=10e-9,
        metric_value=15_915.0,
        objective_value=0.5915,
        status="success",
        simulation_time_seconds=0.01,
        run_directory=str(tmp_path / "output" / "runs" / "evaluation_00001"),
    )
    result = OptimizationResult(
        best_evaluation=best,
        evaluations=(first, best),
        optimizer_success=True,
        optimizer_message="converged",
        iteration_count=2,
        function_evaluation_count=2,
        total_time_seconds=0.03,
    )
    monkeypatch.setattr(
        "circuitpilot.cli.run_circuit_optimization",
        lambda config, output_dir, **kwargs: result,
    )
    database_path = tmp_path / "experiments.sqlite3"
    output_path = tmp_path / "output"

    status = main(
        [
            "--optimize-config",
            str(config_path),
            "--output-dir",
            str(output_path),
            "--experiment-name",
            "CLI RC optimization",
            "--experiment-database",
            str(database_path),
        ]
    )

    captured = capsys.readouterr()
    records = ExperimentRepository(database_path).list_experiments()
    assert status == 0
    assert "Automatic optimization completed" in captured.out
    assert "Best resistance: 1590 ohm" in captured.out
    assert "Experiment saved with ID" in captured.out
    assert (output_path / "optimization_history.csv").is_file()
    assert (output_path / "optimization_summary.json").is_file()
    assert (output_path / "optimization_progress.png").is_file()
    assert len(records) == 1
    assert records[0].metrics["bandwidth_hz"] == pytest.approx(10_007.0)
    assert records[0].metrics["relative_error"] == pytest.approx(0.0007)
