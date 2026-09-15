from copy import deepcopy
from dataclasses import replace
import csv
from hashlib import sha256
import json
from pathlib import Path

import pytest

from circuitpilot.exceptions import FairComparisonError
from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments.task7_batch import validate_fairness
from circuitpilot.experiments.task7_runner import Task7RunDefinition
from circuitpilot.simulator import resolve_ngspice_executable
from circuitpilot.sky130_two_stage_ota import evaluate_task7_full_candidate
from circuitpilot.task6_protocol import (
    TASK5_BENCHMARK_HASH,
    evaluation_policy_family_hash,
)
from circuitpilot.task7_protocol import (
    METHODS,
    TASK7_BENCHMARK_HASH,
    TASK7_COMPONENT_HASHES,
    task7_component_hashes,
)


TASK7_ROOT = Path("research/sky130/two_stage_ota")
FROZEN = TASK7_ROOT / "task7_frozen.yaml"
FORMAL = TASK7_ROOT / "results" / "formal"


def test_task5_and_task6_frozen_hashes_remain_unchanged():
    task5 = load_experiment_config(
        Path("research/sky130/differential_amplifier")
        / "differential_amplifier_frozen.yaml"
    )
    assert task5.computed_benchmark_hash() == TASK5_BENCHMARK_HASH
    assert (
        evaluation_policy_family_hash()
        == "53b1eb73160b4d069135f406613cd1249fcdd002bfd6cb2b0c8892da1c3b4867"
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    (
        (
            Path("research/sky130/differential_amplifier")
            / "differential_amplifier_frozen.yaml",
            "bdcfd6f38367a48a5d16583deb5a02495ca8b3938afbc1b2df1707ba75421f38",
        ),
        (
            Path("research/sky130/differential_amplifier/task6")
            / "task6_frozen.yaml",
            "9e6e720575f729fd4014a465c1123786e3cbf63472377cda9b6864cc332288d4",
        ),
        (
            Path("research/sky130/differential_amplifier/task6/results")
            / "file_hashes.json",
            "17e195aaf7223b55bdbc04bd23999f717f340c0838911bd315243ddb9191e5a8",
        ),
        (
            Path("research/sky130/differential_amplifier")
            / "TASK6_PHYSICS_AWARE_REPORT.md",
            "2247530d2583c83e2aa8350fd41508e6e0b53edc4274b435a516c1ea6a4a662f",
        ),
    ),
)
def test_task5_and_task6_frozen_file_bytes_remain_unchanged(path, expected):
    assert sha256(path.read_bytes()).hexdigest() == expected


def test_task7_hash_changes_when_a_bound_testbench_value_changes():
    config = load_experiment_config(FROZEN)
    changed_circuit = replace(
        config.circuit_config,
        load_capacitance_f=2.0 * config.circuit_config.load_capacitance_f,
    )
    changed = replace(
        config,
        circuit_config=changed_circuit,
        benchmark_config_hash=None,
    )
    assert changed.computed_benchmark_hash() != TASK7_BENCHMARK_HASH


def test_all_four_methods_resolve_to_the_same_task7_benchmark_hash(tmp_path):
    hashes = {
        Task7RunDefinition(
            FROZEN,
            method,
            seed=0,
            candidate_budget=25,
            experiment_design="smoke",
            output_root=tmp_path,
        )
        .resolved_config()
        .computed_benchmark_hash()
        for method in METHODS
    }
    assert hashes == {TASK7_BENCHMARK_HASH}


def test_fairness_validator_rejects_any_benchmark_drift():
    summaries = json.loads((FORMAL / "cell_summaries.json").read_text())
    drifted = deepcopy(summaries)
    drifted[0]["task7_benchmark_hash"] = "0" * 64
    with pytest.raises(FairComparisonError):
        validate_fairness(
            drifted,
            methods=METHODS,
            seeds=tuple(range(10)),
            design="formal",
            candidate_budget=50,
        )
    drifted = deepcopy(summaries)
    drifted[0]["component_hashes"]["topology_hash"] = "0" * 64
    with pytest.raises(FairComparisonError):
        validate_fairness(
            drifted,
            methods=METHODS,
            seeds=tuple(range(10)),
            design="formal",
            candidate_budget=50,
        )


def test_expanded_fairness_evidence_binds_every_required_component():
    evidence = json.loads(
        (FORMAL / "expanded_fairness_validation.json").read_text()
    )
    assert evidence["status"] == "pass"
    assert evidence["component_hashes"] == TASK7_COMPONENT_HASHES
    assert task7_component_hashes(load_experiment_config(FROZEN)) == (
        TASK7_COMPONENT_HASHES
    )
    assert set(evidence["component_hashes"]) == {
        "topology_hash",
        "role_mapping_hash",
        "pdk_hash",
        "model_library_hash",
        "ugf_semantics_hash",
        "phase_margin_semantics_hash",
        "transient_semantics_hash",
        "slew_semantics_hash",
        "load_testbench_hash",
        "cost_model_hash",
        "objective_hash",
    }


def test_status_taxonomy_has_one_complete_row_per_formal_candidate():
    with (FORMAL / "status_taxonomy.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2000
    assert {row["stability_status"] for row in rows} <= {
        "stable",
        "phase_margin_insufficient",
        "no_valid_unity_crossing",
        "invalid_response",
    }
    assert sum(row["simulation_failed"] == "True" for row in rows) == 0


def test_frozen_filename_alias_is_byte_identical():
    assert (TASK7_ROOT / "two_stage_ota_frozen.yaml").read_bytes() == FROZEN.read_bytes()
    assert (TASK7_ROOT / "calibration.csv").read_bytes() == (
        TASK7_ROOT / "results" / "calibration" / "calibration.csv"
    ).read_bytes()


def test_real_sky130_two_stage_ota_full_evaluation(tmp_path):
    config = load_experiment_config(FROZEN)
    executable = resolve_ngspice_executable(config.ngspice_config.executable)
    if executable is None:
        pytest.skip("ngspice is unavailable")
    if config.circuit_config is None or not config.circuit_config.model.model_library.is_file():
        pytest.skip("frozen SKY130 model library is unavailable")
    best = json.loads(
        (FORMAL / "best_raw_evidence" / "index.json").read_text()
    )[0]
    result = evaluate_task7_full_candidate(
        config.circuit_config,
        best["parameters"],
        tmp_path / "evaluation",
        executable=executable,
        timeout_seconds=config.timeout,
        start_frequency_hz=config.ngspice_config.start_frequency_hz,
        stop_frequency_hz=config.ngspice_config.stop_frequency_hz,
        points_per_decade=config.ngspice_config.points_per_decade,
    )
    assert result.errors == {"op": None, "ac": None, "transient": None}
    assert result.operating_point is not None
    assert result.operating_point.dc_power_w > 0.0
    assert result.ac_response is not None
    assert result.transient_response is not None
    assert result.cost.candidate_evaluations == 1
    assert result.cost.ngspice_process_calls == 3
    assert result.cost.op_calls == 1
    assert result.cost.ac_calls == 1
    assert result.cost.transient_calls == 1
    assert result.cost.high_fidelity_analysis_calls == 3
