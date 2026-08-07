from dataclasses import replace
from pathlib import Path

import pytest

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments.recorder import EVALUATION_COLUMNS
from circuitpilot.experiments.runner import execute_experiment
from circuitpilot.parser import parse_ac_output
from circuitpilot.simulator import resolve_ngspice_executable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NGSPICE_EXECUTABLE = resolve_ngspice_executable("ngspice")


@pytest.mark.integration
@pytest.mark.skipif(NGSPICE_EXECUTABLE is None, reason="real ngspice is required")
@pytest.mark.parametrize("method", ("random", "de", "tpe", "bo"))
def test_all_task2_methods_use_real_ngspice_common_runner(tmp_path: Path, method: str) -> None:
    base = load_experiment_config(PROJECT_ROOT / "experiments" / "configs" / f"rc_baseline_{method}.yaml")
    config = replace(
        base,
        simulation_budget=2,
        output_dir=tmp_path / method,
        ngspice_config=replace(base.ngspice_config, executable=NGSPICE_EXECUTABLE or "ngspice"),
    )
    result = execute_experiment(config)
    assert result.budget["evaluations_total"] == 2
    assert result.budget["ngspice_calls"] == 2
    assert result.budget["evaluations_success"] == 2
    assert all(record.raw_metrics["bandwidth"] > 0 for record in result.records)
    assert all(record.objective_value is not None for record in result.records)
    assert all(record.optimizer_phase for record in result.records)
    for record in result.records:
        evidence = result.output_directory / record.run_directory
        assert len(parse_ac_output(evidence / "ac_results.dat")) > 100
        assert (evidence / "ngspice.log").is_file()
        assert (evidence / "rc_lowpass.cir").is_file()
    header = (result.output_directory / "evaluations.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    assert tuple(header) == EVALUATION_COLUMNS
