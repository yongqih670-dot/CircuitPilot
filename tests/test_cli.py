from pathlib import Path

import pytest

from circuitpilot.cli import main
from circuitpilot.exceptions import SimulationError
from circuitpilot.parameter_sweep import SweepResult
from circuitpilot.parser import ACAnalysisResult


def test_main_runs_complete_workflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    response = ACAnalysisResult(
        frequency_hz=(10.0, 100.0, 1_000.0),
        gain_db=(0.0, -3.0, -20.0),
        phase_deg=(-1.0, -45.0, -85.0),
    )
    monkeypatch.setattr("circuitpilot.cli.run_ngspice", lambda *args, **kwargs: None)
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
    monkeypatch.setattr("circuitpilot.cli.run_ngspice", lambda *args, **kwargs: None)
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
    monkeypatch.setattr("circuitpilot.cli.run_ngspice", lambda *args, **kwargs: None)
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
