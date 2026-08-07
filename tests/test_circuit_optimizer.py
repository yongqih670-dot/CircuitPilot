import csv
from math import pi
from pathlib import Path
import re
from types import SimpleNamespace
import sys

import matplotlib
import pytest

matplotlib.use("Agg")

from circuitpilot.circuit_config import ACAnalysisConfig, CircuitType
from circuitpilot.circuit_optimizer import (
    OptimizationEvaluation,
    OptimizationResult,
    evaluate_response_metric,
    metric_to_objective,
    plot_optimization_progress,
    run_circuit_optimization,
    save_optimization_history_csv,
    save_optimization_summary_json,
)
from circuitpilot.exceptions import OptimizationError
from circuitpilot.optimization_config import (
    ObjectiveConfig,
    ObjectiveGoal,
    ObjectiveMetric,
    OptimizationConfig,
    OptimizerSettings,
    ParameterBounds,
    ParameterScale,
)
from circuitpilot.parser import ACAnalysisResult
from circuitpilot.power_metrics import DERIVED_RC_POWER_METRIC


def _config(
    metric: ObjectiveMetric = ObjectiveMetric.BANDWIDTH,
    circuit_type: CircuitType = CircuitType.RC_LOWPASS,
) -> OptimizationConfig:
    if metric is ObjectiveMetric.BANDWIDTH:
        objective = ObjectiveConfig(metric, ObjectiveGoal.TARGET, target_value=1_000.0)
    elif metric is ObjectiveMetric.GAIN:
        objective = ObjectiveConfig(
            metric, ObjectiveGoal.MAXIMIZE, evaluation_frequency_hz=1_000.0
        )
    else:
        objective = ObjectiveConfig(
            metric, ObjectiveGoal.MINIMIZE, evaluation_frequency_hz=1_000.0
        )
    return OptimizationConfig(
        circuit_type=circuit_type,
        resistance=ParameterBounds(100.0, 10_000.0, ParameterScale.LOG),
        capacitance=ParameterBounds(10e-9, 1e-6, ParameterScale.LOG),
        objective=objective,
        analysis=ACAnalysisConfig(10.0, 100_000.0, 50),
        optimizer=OptimizerSettings(2, 3, 1e-3, 42, False),
    )


def test_evaluates_bandwidth_and_target_error() -> None:
    response = ACAnalysisResult(
        frequency_hz=(100.0, 1_000.0, 10_000.0),
        gain_db=(0.0, -3.0, -20.0),
        phase_deg=(-5.0, -45.0, -85.0),
    )
    config = _config()

    metric = evaluate_response_metric(config, response, resistance_ohm=1_000.0)

    assert metric == pytest.approx(1_000.0)
    assert metric_to_objective(config, metric) == pytest.approx(0.0)


def test_evaluates_interpolated_gain_for_maximize() -> None:
    config = _config(ObjectiveMetric.GAIN)
    response = ACAnalysisResult(
        frequency_hz=(100.0, 10_000.0),
        gain_db=(0.0, -20.0),
        phase_deg=(0.0, -90.0),
    )

    metric = evaluate_response_metric(config, response, resistance_ohm=1_000.0)

    assert metric == pytest.approx(-10.0)
    assert metric_to_objective(config, metric) == pytest.approx(10.0)


def test_evaluates_highpass_resistor_power() -> None:
    config = _config(ObjectiveMetric.POWER, CircuitType.RC_HIGHPASS)
    response = ACAnalysisResult(
        frequency_hz=(100.0, 1_000.0, 10_000.0),
        gain_db=(-20.0, 0.0, 0.0),
        phase_deg=(90.0, 0.0, 0.0),
    )

    metric = evaluate_response_metric(config, response, resistance_ohm=1_000.0)

    assert metric == pytest.approx(0.0005)
    assert metric_to_objective(config, metric) == pytest.approx(metric)


def test_power_summary_explicitly_labels_derived_rc_model(tmp_path: Path) -> None:
    evaluation = OptimizationEvaluation(
        1, 1_000.0, 1e-7, 0.0005, 0.0005, "success", 0.01, "run1"
    )
    result = OptimizationResult(
        evaluation, (evaluation,), True, "done", 1, 1, 0.01
    )

    summary = save_optimization_summary_json(
        _config(ObjectiveMetric.POWER), result, tmp_path / "power.json"
    ).read_text(encoding="utf-8")

    assert f'"metric_model": "{DERIVED_RC_POWER_METRIC}"' in summary


def _values_from_netlist(data_path: Path) -> tuple[float, float]:
    netlist = next(data_path.parent.glob("*.cir")).read_text(encoding="utf-8")
    resistance_match = re.search(r"R1 (?:in out|out 0) ([0-9.e+-]+)", netlist)
    capacitance_match = re.search(r"C1 (?:out 0|in out) ([0-9.e+-]+)", netlist)
    assert resistance_match is not None
    assert capacitance_match is not None
    return float(resistance_match.group(1)), float(capacitance_match.group(1))


def test_optimizer_generates_simulations_and_preserves_every_history_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    coordinates = ((2.0, -7.0), (3.0, -6.798179868))

    def fake_optimizer(function: object, **kwargs: object) -> SimpleNamespace:
        values = [function(point) for point in coordinates]  # type: ignore[operator]
        best_index = min(range(len(values)), key=values.__getitem__)
        return SimpleNamespace(
            success=True,
            message="synthetic convergence",
            nit=1,
            nfev=len(values),
            x=coordinates[best_index],
            fun=values[best_index],
        )

    def fake_parse(data_path: Path) -> ACAnalysisResult:
        resistance, capacitance = _values_from_netlist(Path(data_path))
        cutoff = 1.0 / (2.0 * pi * resistance * capacitance)
        return ACAnalysisResult(
            frequency_hz=(cutoff / 10.0, cutoff, cutoff * 10.0),
            gain_db=(0.0, -3.0, -20.0),
            phase_deg=(-5.0, -45.0, -85.0),
        )

    monkeypatch.setattr("circuitpilot.circuit_optimizer.differential_evolution", fake_optimizer)
    monkeypatch.setattr("circuitpilot.circuit_optimizer.run_ngspice", lambda *args, **kwargs: None)
    monkeypatch.setattr("circuitpilot.circuit_optimizer.parse_ac_output", fake_parse)

    result = run_circuit_optimization(_config(), tmp_path, executable=sys.executable)

    assert len(result.evaluations) == 2
    assert result.successful_count == 2
    assert result.failed_count == 0
    assert result.best_evaluation.evaluation_index == 2
    assert result.best_evaluation.metric_value == pytest.approx(1_000.0, rel=1e-6)
    assert Path(result.evaluations[0].run_directory) == Path(
        "runs/evaluation_00001"
    )
    assert len(list((tmp_path / "runs").glob("evaluation_*/*.cir"))) == 2


def test_optimizer_penalizes_failed_candidate_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def fake_optimizer(function: object, **kwargs: object) -> SimpleNamespace:
        values = [function((2.0, -7.0)), function((3.0, -6.798179868))]  # type: ignore[operator]
        return SimpleNamespace(
            success=True,
            message="done",
            nit=1,
            nfev=2,
            x=(3.0, -6.798179868),
            fun=values[1],
        )

    def fake_run(*args: object, **kwargs: object) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OptimizationError("candidate failed")

    def fake_parse(data_path: Path) -> ACAnalysisResult:
        return ACAnalysisResult(
            frequency_hz=(100.0, 1_000.0, 10_000.0),
            gain_db=(0.0, -3.0, -20.0),
            phase_deg=(-5.0, -45.0, -85.0),
        )

    monkeypatch.setattr("circuitpilot.circuit_optimizer.differential_evolution", fake_optimizer)
    monkeypatch.setattr("circuitpilot.circuit_optimizer.run_ngspice", fake_run)
    monkeypatch.setattr("circuitpilot.circuit_optimizer.parse_ac_output", fake_parse)

    result = run_circuit_optimization(_config(), tmp_path, executable=sys.executable)

    assert result.failed_count == 1
    assert result.successful_count == 1
    assert result.evaluations[0].error_message == "candidate failed"
    assert result.best_evaluation.evaluation_index == 2
    history = (tmp_path / "optimization_history.csv").read_text(encoding="utf-8")
    assert "failed" in history
    assert "candidate failed" in history


def test_all_failed_candidates_raise_and_leave_failure_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_optimizer(function: object, **kwargs: object) -> SimpleNamespace:
        values = [function((2.0, -7.0)), function((3.0, -6.8))]  # type: ignore[operator]
        return SimpleNamespace(
            success=False,
            message="all failed",
            nit=1,
            nfev=2,
            x=(2.0, -7.0),
            fun=min(values),
        )

    monkeypatch.setattr(
        "circuitpilot.circuit_optimizer.differential_evolution", fake_optimizer
    )
    monkeypatch.setattr(
        "circuitpilot.circuit_optimizer.run_ngspice",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            OptimizationError("real metric unavailable")
        ),
    )

    with pytest.raises(OptimizationError, match="all optimization evaluations failed"):
        run_circuit_optimization(_config(), tmp_path, executable=sys.executable)

    history_path = tmp_path / "optimization_history.csv"
    rows = list(csv.DictReader(history_path.open(encoding="utf-8", newline="")))
    assert len(rows) == 2
    assert all(row["status"] == "failed" for row in rows)
    assert all(row["metric_value"] == "" for row in rows)


def test_history_summary_and_progress_plot_are_written(tmp_path: Path) -> None:
    evaluations = (
        OptimizationEvaluation(1, 100.0, 1e-7, 2_000.0, 1.0, "success", 0.01, "run1"),
        OptimizationEvaluation(2, 1_000.0, 1.59154943e-7, 1_000.0, 0.0, "success", 0.02, "run2"),
    )
    result = OptimizationResult(
        best_evaluation=evaluations[1],
        evaluations=evaluations,
        optimizer_success=True,
        optimizer_message="converged",
        iteration_count=2,
        function_evaluation_count=2,
        total_time_seconds=0.03,
    )

    csv_path = save_optimization_history_csv(result, tmp_path / "history.csv")
    json_path = save_optimization_summary_json(
        _config(), result, tmp_path / "summary.json"
    )
    plot_path = plot_optimization_progress(
        _config(), result, tmp_path / "progress.png"
    )

    assert "best_objective_so_far" in csv_path.read_text(encoding="utf-8")
    assert '"recorded_evaluation_count": 2' in json_path.read_text(encoding="utf-8")
    assert plot_path.is_file()
    assert plot_path.stat().st_size > 1_000
