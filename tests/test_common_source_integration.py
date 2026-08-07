from __future__ import annotations

from pathlib import Path
from math import isfinite

import pytest

from circuitpilot.experiments.runner import execute_experiment
from circuitpilot.simulator import resolve_ngspice_executable
from test_common_source import experiment_config


@pytest.mark.integration
def test_real_ngspice_common_source_end_to_end(tmp_path: Path) -> None:
    if resolve_ngspice_executable() is None:
        pytest.skip("real ngspice is not installed")
    result = execute_experiment(experiment_config(tmp_path))
    assert result.budget["ngspice_calls"] == 1
    assert result.records[0].simulation_status == "success"
    metrics = result.records[0].raw_metrics
    assert isfinite(metrics["gain_db"])
    assert metrics["bandwidth_hz"] > 0.0
    assert metrics["dc_power_w"] > 0.0
    evidence = result.output_directory / result.records[0].run_directory
    for name in (
        "common_source.cir",
        "ngspice.log",
        "ac_results.dat",
        "dc_operating_point.dat",
        "mos_operating_point.dat",
    ):
        assert (evidence / name).is_file()
    manifest = (result.output_directory / "research_manifest.json").read_text(encoding="utf-8")
    assert '"model_library_sha256"' in manifest
    assert '"benchmark_config_hash"' in manifest
