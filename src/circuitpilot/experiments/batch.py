"""CLI and orchestration for fair multi-method baseline suites."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

import yaml

from circuitpilot.exceptions import CircuitPilotError, ConfigError
from circuitpilot.experiments.baseline_plots import plot_baseline
from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments.fairness import FairnessValidator
from circuitpilot.experiments.runner import execute_experiment
from circuitpilot.experiments.statistics import (
    RESULT_COLUMNS,
    SUMMARY_COLUMNS,
    summarize_methods,
    summarize_run,
    write_table,
)
from circuitpilot.run_directory import prepare_research_run_directory


@dataclass(frozen=True, slots=True)
class BaselineSuiteConfig:
    """Small declarative batch wrapper around unified ExperimentConfig files."""

    name: str
    output_dir: Path
    methods: Mapping[str, Path]
    seeds: tuple[int, ...]
    simulation_budget: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "output_dir": self.output_dir.as_posix(),
            "methods": {method: path.as_posix() for method, path in self.methods.items()},
            "seeds": list(self.seeds),
            "simulation_budget": self.simulation_budget,
        }


def load_suite_config(path: str | Path) -> BaselineSuiteConfig:
    """Read and strictly validate a baseline suite YAML."""
    source = Path(path).resolve()
    try:
        root = yaml.safe_load(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"failed to read baseline suite '{source}': {exc}") from exc
    if not isinstance(root, Mapping) or set(root) != {"suite"} or not isinstance(root["suite"], Mapping):
        raise ConfigError("baseline suite must contain only a suite mapping")
    suite = root["suite"]
    required = {"name", "output_dir", "methods", "seeds", "simulation_budget"}
    if set(suite) != required:
        raise ConfigError("suite fields must be: " + ", ".join(sorted(required)))
    methods = suite["methods"]
    if not isinstance(methods, Mapping) or set(methods) != {"random", "de", "tpe", "bo"}:
        raise ConfigError("suite.methods must define exactly random, de, tpe, and bo")
    resolved_methods: dict[str, Path] = {}
    for method, config_path in methods.items():
        if not isinstance(config_path, str) or not config_path:
            raise ConfigError(f"suite.methods.{method} must be a path")
        candidate = Path(config_path)
        resolved_methods[str(method)] = candidate.resolve() if candidate.is_absolute() else (source.parent / candidate).resolve()
    seeds = suite["seeds"]
    if not isinstance(seeds, list) or not seeds or any(isinstance(seed, bool) or not isinstance(seed, int) or seed < 0 for seed in seeds) or len(set(seeds)) != len(seeds):
        raise ConfigError("suite.seeds must be unique non-negative integers")
    budget = suite["simulation_budget"]
    if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
        raise ConfigError("suite.simulation_budget must be a positive integer")
    name = suite["name"]
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("suite.name must be non-empty")
    output = Path(suite["output_dir"])
    if not output.is_absolute():
        output = (source.parent.parent.parent / output).resolve()
    return BaselineSuiteConfig(name, output, resolved_methods, tuple(seeds), budget)


def run_suite(config: BaselineSuiteConfig) -> Path:
    """Run every method/seed through the same execute_experiment path."""
    payload = json.dumps(config.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    suite_run = prepare_research_run_directory(
        None,
        default_root=config.output_dir,
        configuration_sha256=sha256(payload).hexdigest(),
    )
    (suite_run.path / "baseline_suite_config.json").write_text(
        json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    run_directories: list[Path] = []
    for method, config_path in config.methods.items():
        base = load_experiment_config(config_path)
        if base.method != method:
            raise ConfigError(f"suite method '{method}' points to method='{base.method}' config")
        for seed in config.seeds:
            run_config = replace(
                base,
                experiment_name=f"{config.name}_{method}_seed{seed}",
                seed=seed,
                simulation_budget=config.simulation_budget,
                output_dir=suite_run.path / f"{method}_seed{seed}",
                resume=False,
            )
            result = execute_experiment(run_config)
            run_directories.append(result.output_directory)

    fairness = FairnessValidator().validate(run_directories)
    (suite_run.path / "fairness_validation.json").write_text(
        json.dumps(fairness, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    results = [summarize_run(path) for path in run_directories]
    summaries = summarize_methods(results)
    write_table(suite_run.path / "baseline_results.csv", RESULT_COLUMNS, results)
    write_table(suite_run.path / "baseline_summary.csv", SUMMARY_COLUMNS, summaries)
    plot_baseline(run_directories, suite_run.path / "plots")
    return suite_run.path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a fair traditional-optimizer baseline suite.")
    parser.add_argument("--config", required=True, type=Path, help="baseline suite YAML")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        output = run_suite(load_suite_config(arguments.config))
    except (CircuitPilotError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Baseline output directory: {output}")
    print(f"Results: {output / 'baseline_results.csv'}")
    print(f"Summary: {output / 'baseline_summary.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
