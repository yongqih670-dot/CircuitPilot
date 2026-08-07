from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest

from circuitpilot.common_source import CommonSourceCircuitConfig
from circuitpilot.experiments.calibration import load_calibration_grid
from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments.optimizer import create_optimizer
from circuitpilot.experiments.seeding import initialize_seeds
from circuitpilot.experiments.statistics import summarize_run
from circuitpilot.exceptions import ResearchExperimentError
from circuitpilot.mosfet_model import MosfetModelConfig
from circuitpilot.simulator import resolve_ngspice_executable, run_ngspice


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIRECTORY = ROOT / "experiments" / "configs"
FROZEN = ROOT / "research" / "common_source" / "common_source_frozen.yaml"


def test_common_source_yaml_and_grid_are_strictly_validated() -> None:
    config = load_experiment_config(FROZEN)
    grid = load_calibration_grid(
        ROOT / "research" / "common_source" / "calibration_grid.yaml", config
    )
    assert config.circuit_name == "common_source"
    assert config.circuit_config is not None
    assert config.circuit_config.model.library_sha256() == "e14792f8adbe569d6f4152292343bc9fb0a41364a5aa1a5ad476b82f70316168"
    assert len(grid) == 4
    assert all(parameter.unit for parameter in config.search_space)


def test_all_four_methods_use_identical_frozen_benchmark_hash() -> None:
    methods = ("random", "de", "tpe", "bo")
    configs = [
        load_experiment_config(CONFIG_DIRECTORY / f"common_source_{method}.yaml")
        for method in methods
    ]
    hashes = {config.computed_benchmark_hash() for config in configs}
    assert hashes == {"d60664b436ce9a928da2db86ca83378d556f18ddcf54b633394609f67288bec9"}
    for config in configs:
        assert config.benchmark_config_hash in hashes
        optimizer = create_optimizer(config, initialize_seeds(config.seed))
        assert set(optimizer.ask()) == set(config.search_space_by_name)


def test_calibration_rows_cannot_enter_baseline_summary(tmp_path: Path) -> None:
    columns = (
        "experiment_id,run_id,circuit,method,optimizer_phase,seed,iteration,parameters,"
        "simulation_status,failure_type,error_message,ngspice_return_code,timed_out,"
        "raw_metrics,objective_value,constraint_violation,is_feasible,simulation_time,"
        "total_elapsed_time,timestamp,run_directory,ngspice_called,benchmark_config_hash,"
        "experiment_phase,event_observed,evaluation_time\n"
    )
    row = (
        'cal,run,common_source,random,search,0,1,"{}",simulation_failed,AnalysisError,'
        'error,,false,"{}",,,false,0.1,0.1,2026-01-01T00:00:00Z,runs/calibration_0001,'
        "true,,calibration,false,1\n"
    )
    (tmp_path / "evaluations.csv").write_text(columns + row, encoding="utf-8")
    with pytest.raises(ResearchExperimentError, match="calibration"):
        summarize_run(tmp_path)


@pytest.mark.integration
def test_sky130_common_source_when_environment_is_available(tmp_path: Path) -> None:
    library = os.environ.get("SKY130_MODEL_LIBRARY")
    model_name = os.environ.get("SKY130_MODEL_NAME", "sky130_fd_pr__nfet_01v8")
    section = os.environ.get("SKY130_MODEL_SECTION", "tt")
    if not library:
        pytest.skip("SKY130_MODEL_LIBRARY is not configured")
    if resolve_ngspice_executable() is None:
        pytest.skip("real ngspice is not installed")
    model = MosfetModelConfig(
        Path(library), model_name, section, "user-configured SKY130 PDK", section, "subcircuit"
    )
    circuit = CommonSourceCircuitConfig(1.8, 1e-12, 27.0, model)
    from circuitpilot.common_source import write_common_source_netlist

    netlist = write_common_source_netlist(
        tmp_path / "sky130_common_source.cir",
        circuit,
        {"width_m": 2e-6, "length_m": 0.5e-6, "drain_resistance_ohm": 10e3, "input_bias_v": 0.9},
        ac_output_path=tmp_path / "ac_results.dat",
        op_output_path=tmp_path / "dc_operating_point.dat",
        device_op_output_path=tmp_path / "mos_operating_point.dat",
        start_frequency_hz=10.0,
        stop_frequency_hz=1e9,
        points_per_decade=20,
    )
    result = run_ngspice(netlist, log_path=tmp_path / "ngspice.log")
    assert result.returncode == 0
