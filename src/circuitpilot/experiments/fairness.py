"""Pre-aggregation fairness checks for research baseline runs."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable

from circuitpilot.exceptions import FairComparisonError


def _load_manifest(run_directory: Path) -> dict[str, Any]:
    source = run_directory / "research_manifest.json"
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FairComparisonError(f"cannot read research manifest '{source}': {exc}") from exc
    if not isinstance(payload, dict):
        raise FairComparisonError(f"research manifest '{source}' must be an object")
    return payload


def _stable_hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


class FairnessValidator:
    """Reject comparison of runs that differ in any protocol-controlled field."""

    FIELDS = (
        "search_space_hash",
        "benchmark_config_hash",
        "circuit",
        "circuit_config",
        "transistor_model",
        "model_sha256",
        "pdk_release",
        "pdk_commit",
        "topology_hash",
        "device_role_mapping_hash",
        "differential_testbench_hash",
        "common_mode_testbench_hash",
        "cmrr_semantics_version",
        "bandwidth_semantics_version",
        "measurement_window",
        "censoring_policy",
        "difficulty_protocol_version",
        "simulation_cost_semantics",
        "simulation_budget",
        "experiment_phase",
        "pvt_config",
        "metric_definitions",
        "objectives",
        "constraints",
        "success_criterion",
        "ngspice_config",
        "ngspice_version_string",
        "ngspice_executable_sha256",
        "circuitpilot_version",
        "git_commit_hash",
        "python_version",
        "numpy_version",
        "scipy_version",
        "optuna_version",
    )

    @classmethod
    def _signature(cls, manifest: dict[str, Any]) -> dict[str, Any]:
        try:
            config = manifest["configuration"]
            environment = manifest["environment"]
            experiment = config["experiment"]
            circuit_config = json.loads(json.dumps(config.get("circuit_config")))
            if circuit_config is not None:
                circuit_config.get("mosfet_model", {}).pop("model_library", None)
            transistor_model = json.loads(json.dumps(manifest.get("transistor_model")))
            if transistor_model is not None:
                transistor_model.pop("model_path", None)
                transistor_model.pop("pdk_root", None)
            measurement_window = {
                "start_frequency_hz": config["ngspice_config"]["start_frequency_hz"],
                "stop_frequency_hz": config["ngspice_config"]["stop_frequency_hz"],
                "points_per_decade": config["ngspice_config"]["points_per_decade"],
            }
            return {
                "search_space_hash": _stable_hash(config["search_space"]),
                "benchmark_config_hash": manifest.get("reproducibility", {}).get(
                    "benchmark_config_hash"
                ),
                "circuit": experiment["circuit"],
                "circuit_config": circuit_config,
                "transistor_model": transistor_model,
                "model_sha256": None if transistor_model is None else transistor_model.get("model_sha256"),
                "pdk_release": None if transistor_model is None else transistor_model.get("pdk_release"),
                "pdk_commit": None if transistor_model is None else transistor_model.get("pdk_commit"),
                "topology_hash": (
                    None
                    if circuit_config is None
                    else _stable_hash(circuit_config.get("topology_definition"))
                ),
                "device_role_mapping_hash": (
                    None
                    if circuit_config is None
                    else _stable_hash(circuit_config.get("device_role_mapping"))
                ),
                "differential_testbench_hash": (
                    None
                    if circuit_config is None
                    else _stable_hash(
                        circuit_config.get("differential_testbench_definition")
                    )
                ),
                "common_mode_testbench_hash": (
                    None
                    if circuit_config is None
                    else _stable_hash(
                        circuit_config.get("common_mode_testbench_definition")
                    )
                ),
                "cmrr_semantics_version": None if circuit_config is None else circuit_config.get("cmrr_semantics_version"),
                "bandwidth_semantics_version": None if circuit_config is None else circuit_config.get("bandwidth_semantics_version"),
                "measurement_window": measurement_window,
                "censoring_policy": None if circuit_config is None else circuit_config.get("censoring_policy"),
                "difficulty_protocol_version": None if circuit_config is None else circuit_config.get("difficulty_protocol_version"),
                "simulation_cost_semantics": None if circuit_config is None else circuit_config.get("simulation_cost_semantics"),
                "simulation_budget": experiment["simulation_budget"],
                "experiment_phase": experiment.get("phase", "baseline"),
                "pvt_config": config.get("pvt_config", {}),
                "metric_definitions": config["metric_definitions"],
                "objectives": config["objectives"],
                "constraints": config.get("constraints", {}),
                "success_criterion": config["success_criterion"],
                "ngspice_config": config["ngspice_config"],
                "ngspice_version_string": environment["ngspice_version_string"],
                "ngspice_executable_sha256": environment["ngspice_executable_sha256"],
                "circuitpilot_version": environment["circuitpilot_version"],
                "git_commit_hash": environment["git_commit_hash"],
                "python_version": environment["python_version"],
                "numpy_version": environment["numpy_version"],
                "scipy_version": environment["scipy_version"],
                "optuna_version": environment["optuna_version"],
                "git_worktree_dirty": environment.get("git_worktree_dirty"),
            }
        except (KeyError, TypeError) as exc:
            raise FairComparisonError(f"manifest is missing fairness field: {exc}") from exc

    def validate(self, run_directories: Iterable[str | Path]) -> dict[str, Any]:
        """Validate shared conditions and equal seed sets across all methods."""
        paths = [Path(path).resolve() for path in run_directories]
        if not paths:
            raise FairComparisonError("at least one run is required for comparison")
        manifests = [_load_manifest(path) for path in paths]
        reference = self._signature(manifests[0])
        if reference["git_worktree_dirty"] is not False:
            raise FairComparisonError("fair baseline comparison requires a clean Git worktree")
        for path, manifest in zip(paths[1:], manifests[1:]):
            signature = self._signature(manifest)
            if signature["git_worktree_dirty"] is not False:
                raise FairComparisonError(f"run '{path}' was produced from a dirty Git worktree")
            mismatches = [field for field in self.FIELDS if signature[field] != reference[field]]
            if mismatches:
                raise FairComparisonError(
                    f"run '{path}' is not fairly comparable; mismatched: {', '.join(mismatches)}"
                )
        seeds_by_method: dict[str, set[int]] = {}
        for manifest in manifests:
            try:
                experiment = manifest["configuration"]["experiment"]
                method = str(experiment["method"])
                seed = int(experiment["seed"])
            except (KeyError, TypeError, ValueError) as exc:
                raise FairComparisonError(f"manifest has invalid method/seed: {exc}") from exc
            seeds_by_method.setdefault(method, set()).add(seed)
        seed_sets = list(seeds_by_method.values())
        if seed_sets and any(seed_set != seed_sets[0] for seed_set in seed_sets[1:]):
            readable = ", ".join(f"{method}={sorted(seeds)}" for method, seeds in sorted(seeds_by_method.items()))
            raise FairComparisonError(f"methods do not share the same seed set: {readable}")
        return {**reference, "seed_set": sorted(seed_sets[0]) if seed_sets else []}
