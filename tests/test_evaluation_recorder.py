import csv
import json
from pathlib import Path

from circuitpilot.experiments.recorder import (
    EVALUATION_COLUMNS,
    EvaluationRecord,
    EvaluationRecorder,
)


def test_failed_evaluation_has_uniform_csv_and_sqlite_schema(tmp_path: Path) -> None:
    recorder = EvaluationRecorder(tmp_path)
    record = EvaluationRecord.now(
        experiment_id="record_test",
        run_id="cp-20260807T000000000000Z-000000000000",
        circuit="rc_lowpass",
        method="random",
        seed=0,
        iteration=1,
        parameters={"resistance": 1000.0, "capacitance": 1e-7},
        simulation_status="simulation_failed",
        failure_type="SimulationError",
        raw_metrics={},
        objective_value=None,
        constraint_violation=None,
        simulation_time=0.01,
        total_elapsed_time=0.02,
        run_directory="runs/evaluation_0001",
        ngspice_called=True,
    )

    recorder.save(record)

    assert recorder.records() == (record,)
    with recorder.csv_path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
    assert tuple(reader.fieldnames or ()) == EVALUATION_COLUMNS
    assert len(rows) == 1
    assert json.loads(rows[0]["parameters"]) == record.parameters
    assert json.loads(rows[0]["raw_metrics"]) == {}
    assert rows[0]["objective_value"] == ""
    assert rows[0]["simulation_status"] == "simulation_failed"
