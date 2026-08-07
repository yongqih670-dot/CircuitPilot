import json
from pathlib import Path
import sys

import pytest

from circuitpilot.exceptions import ResearchArtifactError
from circuitpilot.research_artifacts import write_research_manifest
from circuitpilot.run_directory import prepare_research_run_directory


def test_manifest_snapshots_config_hashes_evidence_and_records_seed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output = tmp_path / "independent_run"
    run = prepare_research_run_directory(output)
    source_config = tmp_path / "source.yaml"
    source_config.write_text("circuit: rc_lowpass\n", encoding="utf-8")
    (output / "candidate.cir").write_text("* real generated netlist\n", encoding="utf-8")
    (output / "ngspice.log").write_text("ngspice run log\n", encoding="utf-8")
    (output / "ac_results.dat").write_text("1 0 0\n", encoding="utf-8")
    fingerprint = {
        "git_commit_hash": "a" * 40,
        "python_version": "3.12.7",
        "os_information": {"system": "test"},
        "numpy_version": "2.5.1",
        "scipy_version": "1.18.0",
        "pyyaml_version": "6.0.3",
        "ngspice_version_string": "ngspice-46",
        "ngspice_executable_path": sys.executable,
        "ngspice_executable_sha256": "b" * 64,
        "circuitpilot_version": "0.5.0",
        "research_baseline_version": "v0.5-research-baseline",
    }
    monkeypatch.setattr(
        "circuitpilot.research_artifacts.collect_environment_fingerprint",
        lambda executable: fingerprint,
    )

    manifest_path = write_research_manifest(
        output,
        workflow="optimization",
        circuit_type="rc_lowpass",
        configuration={"target_hz": 1_000.0},
        parameters={"R": 1_000.0, "C": 159e-9},
        metrics={"bandwidth_hz": 1_000.0},
        runtime_seconds=0.25,
        ngspice_executable=sys.executable,
        random_seed=17,
        seed_registry={
            "experiment": 17,
            "python_random": 17,
            "numpy_generator": 17,
        },
        run_id=run.run_id,
        resumed=False,
        resume_count=0,
        source_config_path=source_config,
        experiment_name="manifest test",
        experiment_id=1,
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = {item["path"]: item for item in manifest["artifacts"]}
    assert manifest["reproducibility"]["random_seed"] == 17
    assert manifest["reproducibility"]["seeds"]["experiment"] == 17
    assert manifest["schema_version"] == 2
    assert manifest["run"] == {
        "run_id": run.run_id,
        "resumed": False,
        "resume_count": 0,
    }
    assert manifest["environment"] == fingerprint
    assert manifest["reproducibility"]["metric_source"] == "parsed_ngspice_output"
    assert manifest["timing"]["runtime_seconds"] == pytest.approx(0.25)
    assert (output / "input_config.yaml").read_bytes() == source_config.read_bytes()
    assert artifacts["candidate.cir"]["category"] == "netlist"
    assert artifacts["ngspice.log"]["category"] == "ngspice_log"
    assert len(artifacts["ac_results.dat"]["sha256"]) == 64


def test_manifest_refuses_missing_ngspice_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = prepare_research_run_directory(tmp_path / "run")
    monkeypatch.setattr(
        "circuitpilot.research_artifacts.collect_environment_fingerprint",
        lambda executable: {"ngspice_executable_path": sys.executable},
    )
    with pytest.raises(ResearchArtifactError, match="no SPICE netlist"):
        write_research_manifest(
            run.path,
            workflow="simulation",
            circuit_type="rc_lowpass",
            configuration={},
            parameters={},
            metrics={},
            runtime_seconds=0.0,
            ngspice_executable=sys.executable,
            random_seed=None,
            run_id=run.run_id,
            resumed=False,
            resume_count=0,
        )
