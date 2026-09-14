import json
from pathlib import Path

import pytest

from circuitpilot.exceptions import FairComparisonError
from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments.fairness import FairnessValidator


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _manifest(directory: Path, method: str = "random", seed: int = 0, **changes) -> Path:
    config = load_experiment_config(PROJECT_ROOT / "experiments" / "configs" / f"rc_baseline_{method}.yaml").to_dict()
    config["experiment"]["seed"] = seed
    for field, value in changes.items():
        if field == "simulation_budget":
            config["experiment"][field] = value
        else:
            config[field] = value
    directory.mkdir(parents=True)
    (directory / "research_manifest.json").write_text(json.dumps({
        "configuration": config,
        "environment": {
            "ngspice_version_string": "ngspice-46",
            "ngspice_executable_sha256": "a" * 64,
            "circuitpilot_version": "0.5.0",
            "git_commit_hash": "b" * 40,
            "git_worktree_dirty": False,
            "python_version": "3.12.7",
            "numpy_version": "2.5.1",
            "scipy_version": "1.18.0",
            "optuna_version": "4.9.0",
        },
    }), encoding="utf-8")
    return directory


def test_baseline_configs_share_all_protocol_conditions() -> None:
    configs = [load_experiment_config(PROJECT_ROOT / "experiments" / "configs" / f"rc_baseline_{method}.yaml") for method in ("random", "de", "tpe", "bo")]
    reference = configs[0]
    for config in configs[1:]:
        assert config.search_space_sha256() == reference.search_space_sha256()
        assert config.objectives == reference.objectives
        assert config.constraints == reference.constraints
        assert config.success_criterion == reference.success_criterion
        assert config.ngspice_config == reference.ngspice_config
        assert config.pvt_config == reference.pvt_config


@pytest.mark.parametrize(
    ("changes", "match"),
    (
        ({"simulation_budget": 19}, "simulation_budget"),
        ({"search_space": {"resistance": {"type": "float", "low": 1, "high": 2, "log": False}}}, "search_space_hash"),
        ({"success_criterion": {"metric": "bandwidth", "relative_error_threshold": 0.1}}, "success_criterion"),
    ),
)
def test_fairness_validator_rejects_mismatched_conditions(tmp_path: Path, changes: dict, match: str) -> None:
    first = _manifest(tmp_path / "a", "random")
    second = _manifest(tmp_path / "b", "de", **changes)
    with pytest.raises(FairComparisonError, match=match):
        FairnessValidator().validate([first, second])


def test_fairness_validator_rejects_different_seed_sets(tmp_path: Path) -> None:
    paths = [
        _manifest(tmp_path / "random0", "random", 0),
        _manifest(tmp_path / "random1", "random", 1),
        _manifest(tmp_path / "de0", "de", 0),
    ]
    with pytest.raises(FairComparisonError, match="seed set"):
        FairnessValidator().validate(paths)
