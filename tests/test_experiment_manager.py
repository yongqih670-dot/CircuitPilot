from pathlib import Path

import pytest

from circuitpilot.circuit_config import CircuitType
from circuitpilot.exceptions import ExperimentError
from circuitpilot.experiment_manager import ExperimentRepository


def _create(
    repository: ExperimentRepository,
    *,
    name: str,
    error: float,
    cutoff: float,
    created_at: str,
    circuit_type: CircuitType = CircuitType.RC_LOWPASS,
):
    return repository.create_experiment(
        name=name,
        circuit_type=circuit_type,
        parameters={"R": 1000, "C": 159.154943e-9},
        simulation_time_seconds=0.05,
        metrics={"relative_error": error, "cutoff_frequency_hz": cutoff},
        created_at=created_at,
    )


def test_create_experiment_initializes_sqlite_and_round_trips_json(
    tmp_path: Path,
) -> None:
    database = tmp_path / "history" / "experiments.sqlite3"
    repository = ExperimentRepository(database)

    created = _create(
        repository,
        name="baseline",
        error=0.1,
        cutoff=900.0,
        created_at="2026-01-01T00:00:00+00:00",
    )
    loaded = repository.get_experiment(created.experiment_id)

    assert database.is_file()
    assert loaded.name == "baseline"
    assert loaded.circuit_type == "rc_lowpass"
    assert loaded.parameters["R"] == 1000
    assert loaded.metrics["relative_error"] == pytest.approx(0.1)


def test_list_experiments_filters_type_and_orders_newest_first(tmp_path: Path) -> None:
    repository = ExperimentRepository(tmp_path / "experiments.sqlite3")
    first = _create(
        repository,
        name="old lowpass",
        error=0.2,
        cutoff=800.0,
        created_at="2026-01-01T00:00:00+00:00",
    )
    second = _create(
        repository,
        name="new lowpass",
        error=0.1,
        cutoff=900.0,
        created_at="2026-02-01T00:00:00+00:00",
    )
    _create(
        repository,
        name="highpass",
        error=0.05,
        cutoff=950.0,
        created_at="2026-03-01T00:00:00+00:00",
        circuit_type=CircuitType.RC_HIGHPASS,
    )

    records = repository.list_experiments(circuit_type="rc_lowpass")

    assert [record.experiment_id for record in records] == [
        second.experiment_id,
        first.experiment_id,
    ]


def test_show_best_result_supports_minimize_and_maximize(tmp_path: Path) -> None:
    repository = ExperimentRepository(tmp_path / "experiments.sqlite3")
    _create(
        repository,
        name="first",
        error=0.2,
        cutoff=800.0,
        created_at="2026-01-01T00:00:00+00:00",
    )
    best_error = _create(
        repository,
        name="best error",
        error=0.01,
        cutoff=990.0,
        created_at="2026-02-01T00:00:00+00:00",
    )

    minimum = repository.show_best_result("relative_error")
    maximum = repository.show_best_result("cutoff_frequency_hz", minimize=False)

    assert minimum.experiment_id == best_error.experiment_id
    assert maximum.experiment_id == best_error.experiment_id


def test_compare_experiments_uses_first_id_as_baseline(tmp_path: Path) -> None:
    repository = ExperimentRepository(tmp_path / "experiments.sqlite3")
    baseline = _create(
        repository,
        name="baseline",
        error=0.2,
        cutoff=800.0,
        created_at="2026-01-01T00:00:00+00:00",
    )
    improved = _create(
        repository,
        name="improved",
        error=0.05,
        cutoff=950.0,
        created_at="2026-02-01T00:00:00+00:00",
    )

    comparison = repository.compare_experiments(
        "cutoff_frequency_hz",
        experiment_ids=[baseline.experiment_id, improved.experiment_id],
    )

    assert comparison[0].difference_from_baseline == pytest.approx(0.0)
    assert comparison[1].difference_from_baseline == pytest.approx(150.0)
    assert comparison[1].relative_difference_from_baseline == pytest.approx(0.1875)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"name": ""}, "name"),
        ({"simulation_time_seconds": -1}, "simulation_time_seconds"),
        ({"metrics": {}}, "metrics"),
        ({"metrics": {"error": float("nan")}}, "finite"),
        ({"circuit_type": "unknown"}, "unsupported circuit_type"),
    ],
)
def test_create_experiment_rejects_invalid_values(
    tmp_path: Path, kwargs: dict[str, object], message: str
) -> None:
    repository = ExperimentRepository(tmp_path / "experiments.sqlite3")
    arguments = {
        "name": "valid",
        "circuit_type": "rc_lowpass",
        "parameters": {"R": 1000},
        "simulation_time_seconds": 0.1,
        "metrics": {"relative_error": 0.1},
    }
    arguments.update(kwargs)

    with pytest.raises(ExperimentError, match=message):
        repository.create_experiment(**arguments)  # type: ignore[arg-type]


def test_missing_metric_and_short_comparison_raise_clear_errors(tmp_path: Path) -> None:
    repository = ExperimentRepository(tmp_path / "experiments.sqlite3")
    experiment = _create(
        repository,
        name="only",
        error=0.1,
        cutoff=900.0,
        created_at="2026-01-01T00:00:00+00:00",
    )

    with pytest.raises(ExperimentError, match="no experiments contain metric"):
        repository.show_best_result("missing")
    with pytest.raises(ExperimentError, match="at least two"):
        repository.compare_experiments(
            "relative_error", experiment_ids=[experiment.experiment_id]
        )

