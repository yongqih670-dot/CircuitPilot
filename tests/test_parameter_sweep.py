from math import pi
from pathlib import Path
import re
import sys

import matplotlib
import pytest

matplotlib.use("Agg")

from circuitpilot.circuit_config import ACAnalysisConfig, CircuitType
from circuitpilot.exceptions import SimulationError, SweepError
from circuitpilot.parameter_sweep import (
    SweepResult,
    calculate_relative_error,
    format_top_solutions,
    plot_sweep_performance,
    rank_solutions,
    run_parameter_sweep,
    save_sweep_results_csv,
)
from circuitpilot.parser import ACAnalysisResult
from circuitpilot.sweep_config import SweepConfig


def _config(circuit_type: CircuitType = CircuitType.RC_LOWPASS) -> SweepConfig:
    return SweepConfig(
        target_cutoff_frequency_hz=1_000.0,
        resistance_values_ohm=(1_000.0, 2_000.0),
        capacitance_values_f=(100e-9, 200e-9),
        analysis=ACAnalysisConfig(10.0, 100_000.0, 50),
        circuit_type=circuit_type,
        top_n=3,
    )


def _values_from_netlist(data_path: Path) -> tuple[float, float]:
    netlist_path = next(data_path.parent.glob("*.cir"))
    text = netlist_path.read_text(encoding="utf-8")
    resistance = float(re.search(r"R1 (?:in out|out 0) ([0-9.e+-]+)", text).group(1))  # type: ignore[union-attr]
    capacitance = float(re.search(r"C1 (?:out 0|in out) ([0-9.e+-]+)", text).group(1))  # type: ignore[union-attr]
    return resistance, capacitance


def test_run_parameter_sweep_generates_and_measures_every_combination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invoked_netlists: list[Path] = []

    def fake_run(netlist_path: Path, **kwargs: object) -> None:
        invoked_netlists.append(Path(netlist_path))

    def fake_parse(data_path: Path) -> ACAnalysisResult:
        resistance, capacitance = _values_from_netlist(Path(data_path))
        cutoff = 1.0 / (2.0 * pi * resistance * capacitance)
        return ACAnalysisResult(
            frequency_hz=(cutoff / 10.0, cutoff, cutoff * 10.0),
            gain_db=(0.0, -3.0, -20.0),
            phase_deg=(-5.0, -45.0, -85.0),
        )

    monkeypatch.setattr("circuitpilot.parameter_sweep.run_ngspice", fake_run)
    monkeypatch.setattr("circuitpilot.parameter_sweep.parse_ac_output", fake_parse)

    results = run_parameter_sweep(_config(), tmp_path, executable=sys.executable)

    assert len(results) == 4
    assert all(result.succeeded for result in results)
    assert len(invoked_netlists) == 4
    assert len({path.parent for path in invoked_netlists}) == 4
    assert {(result.resistance_ohm, result.capacitance_f) for result in results} == {
        (1_000.0, 100e-9),
        (1_000.0, 200e-9),
        (2_000.0, 100e-9),
        (2_000.0, 200e-9),
    }
    expected = abs(results[0].simulated_cutoff_frequency_hz - 1_000.0) / 1_000.0  # type: ignore[operator]
    assert results[0].relative_error == pytest.approx(expected)


def test_run_parameter_sweep_uses_rising_cutoff_for_highpass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "circuitpilot.parameter_sweep.run_ngspice", lambda *args, **kwargs: None
    )

    def fake_parse(data_path: Path) -> ACAnalysisResult:
        return ACAnalysisResult(
            frequency_hz=(100.0, 1_000.0, 10_000.0),
            gain_db=(-20.0, -3.0, 0.0),
            phase_deg=(85.0, 45.0, 5.0),
        )

    monkeypatch.setattr("circuitpilot.parameter_sweep.parse_ac_output", fake_parse)

    results = run_parameter_sweep(
        _config(CircuitType.RC_HIGHPASS), tmp_path, executable=sys.executable
    )

    assert all(result.simulated_cutoff_frequency_hz == pytest.approx(1_000.0) for result in results)
    assert all(result.relative_error == pytest.approx(0.0) for result in results)


def test_run_parameter_sweep_records_failure_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    call_count = 0

    def fake_run(*args: object, **kwargs: object) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise SimulationError("synthetic ngspice failure")

    monkeypatch.setattr("circuitpilot.parameter_sweep.run_ngspice", fake_run)
    monkeypatch.setattr(
        "circuitpilot.parameter_sweep.parse_ac_output",
        lambda path: ACAnalysisResult(
            (100.0, 1_000.0, 10_000.0),
            (0.0, -3.0, -20.0),
            (-5.0, -45.0, -85.0),
        ),
    )

    results = run_parameter_sweep(_config(), tmp_path, executable=sys.executable)

    assert call_count == 4
    assert [result.status for result in results] == [
        "success",
        "failed",
        "success",
        "success",
    ]
    assert "synthetic ngspice failure" in results[1].error_message


def _result(index: int, error: float) -> SweepResult:
    return SweepResult(
        run_index=index,
        resistance_ohm=float(index * 100),
        capacitance_f=1e-9,
        target_cutoff_frequency_hz=10_000.0,
        simulated_cutoff_frequency_hz=10_000.0 * (1.0 + error),
        relative_error=error,
        status="success",
    )


def test_rank_and_format_top_solutions_order_by_error() -> None:
    results = (_result(1, 0.2), _result(2, 0.01), _result(3, 0.1))

    ranked = rank_solutions(results, top_n=2)
    table = format_top_solutions(results, top_n=2)

    assert [result.run_index for result in ranked] == [2, 3]
    assert table.startswith("Top 2 solutions")
    assert "0.01" in table


def test_save_csv_and_plot_performance(tmp_path: Path) -> None:
    results = (
        _result(1, 0.2),
        _result(2, 0.01),
        SweepResult(
            run_index=3,
            resistance_ohm=300.0,
            capacitance_f=10e-9,
            target_cutoff_frequency_hz=10_000.0,
            simulated_cutoff_frequency_hz=None,
            relative_error=None,
            status="failed",
            error_message="simulation failed",
        ),
    )

    csv_path = save_sweep_results_csv(results, tmp_path / "sweep_results.csv")
    plot_path = plot_sweep_performance(
        results,
        tmp_path / "parameter_performance.png",
        target_cutoff_frequency_hz=10_000.0,
    )

    csv_text = csv_path.read_text(encoding="utf-8")
    assert "relative_error,status,error_message" in csv_text
    assert "simulation failed" in csv_text
    assert plot_path.is_file()
    assert plot_path.stat().st_size > 1_000


def test_calculate_relative_error_matches_specification() -> None:
    assert calculate_relative_error(9_000.0, 10_000.0) == pytest.approx(0.1)


def test_run_parameter_sweep_fails_fast_when_ngspice_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "circuitpilot.parameter_sweep.resolve_ngspice_executable", lambda _: None
    )

    with pytest.raises(SweepError, match="was not found"):
        run_parameter_sweep(_config(), tmp_path, executable="missing-ngspice")

    assert not (tmp_path / "runs").exists()
