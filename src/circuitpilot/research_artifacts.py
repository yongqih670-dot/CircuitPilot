"""Reproducibility manifests for completed CircuitPilot research runs."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from typing import Any, Mapping

from circuitpilot.circuit_config import CircuitType
from circuitpilot.environment_fingerprint import collect_environment_fingerprint
from circuitpilot.exceptions import ResearchArtifactError
from circuitpilot.run_directory import (
    INPUT_CONFIG_FILENAME,
    RUN_CONTEXT_FILENAME,
    mark_run_successful,
)


RESEARCH_MANIFEST_SCHEMA_VERSION = 2
RESEARCH_MANIFEST_FILENAME = "research_manifest.json"


def _json_value(value: Any) -> Any:
    """Convert typed configuration data to deterministic JSON-compatible data."""
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _validate_runtime(runtime_seconds: float) -> float:
    """Require a measured, finite, non-negative run duration."""
    if (
        isinstance(runtime_seconds, bool)
        or not isinstance(runtime_seconds, (int, float))
        or not isfinite(float(runtime_seconds))
        or runtime_seconds < 0
    ):
        raise ResearchArtifactError("runtime_seconds must be finite and non-negative")
    return float(runtime_seconds)


def _copy_input_config(source: str | Path, output_root: Path) -> Path:
    """Copy the exact user YAML bytes into the independent run directory."""
    source_path = Path(source).resolve()
    if not source_path.is_file():
        raise ResearchArtifactError(f"input configuration does not exist: '{source_path}'")
    destination = output_root / INPUT_CONFIG_FILENAME
    try:
        contents = source_path.read_bytes()
        destination.write_bytes(contents)
    except OSError as exc:
        raise ResearchArtifactError(
            f"failed to snapshot input configuration '{source_path}': {exc}"
        ) from exc
    return destination


def _classify_artifact(path: Path) -> str:
    """Return a stable research artifact category for one file."""
    if path.name in {INPUT_CONFIG_FILENAME, RUN_CONTEXT_FILENAME}:
        return "configuration"
    if path.suffix.lower() == ".cir":
        return "netlist"
    if path.name.lower() == "ngspice.log":
        return "ngspice_log"
    if path.name.lower() == "ac_results.dat":
        return "ngspice_output"
    if path.suffix.lower() == ".csv":
        return "tabular_result"
    if path.suffix.lower() == ".png":
        return "plot"
    if path.suffix.lower() == ".json":
        return "result_summary"
    return "other"


def _inventory_artifacts(output_root: Path) -> list[dict[str, Any]]:
    """Hash every run artifact except the manifest being generated."""
    artifacts: list[dict[str, Any]] = []
    try:
        files = sorted(
            path
            for path in output_root.rglob("*")
            if path.is_file() and path.name != RESEARCH_MANIFEST_FILENAME
        )
        for path in files:
            payload = path.read_bytes()
            artifacts.append(
                {
                    "path": path.relative_to(output_root).as_posix(),
                    "category": _classify_artifact(path),
                    "size_bytes": len(payload),
                    "sha256": sha256(payload).hexdigest(),
                }
            )
    except OSError as exc:
        raise ResearchArtifactError(
            f"failed to inventory research artifacts in '{output_root}': {exc}"
        ) from exc
    categories = {artifact["category"] for artifact in artifacts}
    if "netlist" not in categories:
        raise ResearchArtifactError("research run contains no SPICE netlist")
    if "ngspice_log" not in categories:
        raise ResearchArtifactError("research run contains no ngspice log")
    if "ngspice_output" not in categories:
        raise ResearchArtifactError("research run contains no ngspice output data")
    return artifacts


def write_research_manifest(
    output_directory: str | Path,
    *,
    workflow: str,
    circuit_type: str | CircuitType,
    configuration: Mapping[str, Any],
    parameters: Mapping[str, Any],
    metrics: Mapping[str, Any],
    runtime_seconds: float,
    ngspice_executable: str,
    random_seed: int | None,
    run_id: str,
    resumed: bool,
    resume_count: int,
    source_config_path: str | Path | None = None,
    experiment_name: str | None = None,
    experiment_id: int | None = None,
) -> Path:
    """Write a self-contained, hash-inventoried research run manifest.

    The output directory is the experiment boundary. It must already contain
    at least one generated netlist, ngspice log, and raw ngspice data file.
    When a YAML source was used, its exact bytes are copied into this directory.

    Args:
        output_directory: Independent directory produced by one CLI workflow.
        workflow: ``simulation``, ``parameter_sweep``, or ``optimization``.
        circuit_type: Circuit template identifier.
        configuration: Fully resolved configuration snapshot.
        parameters: Simulated or searched component parameters.
        metrics: Metrics derived from parsed ngspice output.
        runtime_seconds: Measured simulation or workflow duration.
        ngspice_executable: Requested executable name or path.
        random_seed: Optimizer seed, or ``None`` for deterministic workflows.
        run_id: Immutable identifier from the prepared run directory.
        resumed: Whether this invocation explicitly resumed that run.
        resume_count: Number of explicit resumes recorded for this run.
        source_config_path: Optional source YAML copied as ``input_config.yaml``.
        experiment_name: Optional SQLite experiment name.
        experiment_id: Optional SQLite primary key.

    Returns:
        Absolute path to ``research_manifest.json``.

    Raises:
        ResearchArtifactError: If required evidence is missing or cannot be saved.
    """
    if workflow not in {"simulation", "parameter_sweep", "optimization"}:
        raise ResearchArtifactError(f"unsupported research workflow '{workflow}'")
    if isinstance(circuit_type, CircuitType):
        circuit_name = circuit_type.value
    elif isinstance(circuit_type, str) and circuit_type:
        circuit_name = circuit_type
    else:
        raise ResearchArtifactError("circuit_type must be a non-empty string")
    if random_seed is not None and (
        isinstance(random_seed, bool) or not isinstance(random_seed, int)
    ):
        raise ResearchArtifactError("random_seed must be an integer or null")
    if not isinstance(run_id, str) or not run_id:
        raise ResearchArtifactError("run_id must be a non-empty string")
    if not isinstance(resumed, bool):
        raise ResearchArtifactError("resumed must be a boolean")
    if (
        isinstance(resume_count, bool)
        or not isinstance(resume_count, int)
        or resume_count < 0
    ):
        raise ResearchArtifactError("resume_count must be a non-negative integer")
    if experiment_id is not None and (
        isinstance(experiment_id, bool)
        or not isinstance(experiment_id, int)
        or experiment_id <= 0
    ):
        raise ResearchArtifactError("experiment_id must be a positive integer or null")

    output_root = Path(output_directory).resolve()
    try:
        output_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ResearchArtifactError(
            f"failed to create research output directory '{output_root}': {exc}"
        ) from exc
    if source_config_path is not None:
        _copy_input_config(source_config_path, output_root)

    environment = collect_environment_fingerprint(ngspice_executable)
    runtime = _validate_runtime(runtime_seconds)
    completed_at = datetime.now(timezone.utc)
    started_at = completed_at - timedelta(seconds=runtime)
    mark_run_successful(output_root, run_id)
    artifacts = _inventory_artifacts(output_root)
    manifest = {
        "schema_version": RESEARCH_MANIFEST_SCHEMA_VERSION,
        "status": "success",
        "run": {
            "run_id": run_id,
            "resumed": resumed,
            "resume_count": resume_count,
        },
        "workflow": workflow,
        "circuit_type": circuit_name,
        "experiment": {
            "name": experiment_name,
            "database_id": experiment_id,
        },
        "timing": {
            "started_at_utc": started_at.isoformat(timespec="microseconds"),
            "completed_at_utc": completed_at.isoformat(timespec="microseconds"),
            "runtime_seconds": runtime,
        },
        "reproducibility": {
            "random_seed": random_seed,
            "ngspice_executable": environment["ngspice_executable_path"],
            "metric_source": "parsed_ngspice_output",
            "raw_output_required": True,
        },
        "environment": environment,
        "configuration": _json_value(configuration),
        "parameters": _json_value(parameters),
        "metrics": _json_value(metrics),
        "artifacts": artifacts,
    }
    destination = output_root / RESEARCH_MANIFEST_FILENAME
    try:
        destination.write_text(
            json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ResearchArtifactError(
            f"failed to write research manifest '{destination}': {exc}"
        ) from exc
    return destination
