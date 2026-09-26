"""Explicit corrected Benchmark-v2 execution boundary for Task 9.6."""

from __future__ import annotations

from math import isfinite, ulp
from pathlib import Path
from typing import Any, Mapping, Sequence

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.task9_5_benchmark import TASK7_SEARCH_SPACE_HASH, benchmark_v2_hash
from circuitpilot.task9_5_evaluator import evaluate_v2_candidate as evaluate_task9_5_v2_candidate
from circuitpilot.task9_5_region import V2_SEMANTICS
from circuitpilot.task9_6_feedback import summarize_v2_robust_feedback


ROOT = Path(__file__).resolve().parents[2]
FROZEN_TASK7_CONFIG = ROOT / "research/sky130/two_stage_ota/task7_frozen.yaml"
APPROVED_BENCHMARK_V2_HASH = "8f622a92370e33ea6f608d7a31077096b8188b868dc070cebbf3ce67f9059708"


def canonicalize_v2_parameters(
    parameters: Mapping[str, float | int],
) -> tuple[dict[str, float | int], dict[str, dict[str, float]]]:
    """Enforce frozen global bounds, allowing only four-ULP boundary noise."""
    frozen = load_experiment_config(FROZEN_TASK7_CONFIG)
    if frozen.search_space_sha256() != TASK7_SEARCH_SPACE_HASH:
        raise RuntimeError("frozen Task 7 search-space identity changed")
    expected = {item.name for item in frozen.search_space}
    if set(parameters) != expected:
        raise ValueError("Task 9.6 requires exactly the 12 frozen design variables")
    canonical = {}
    roundoff = {}
    for item in frozen.search_space:
        value = parameters[item.name]
        if item.contains(value):
            canonical[item.name] = value
            continue
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError(f"invalid Task 9.6 parameter: {item.name}")
        numeric = float(value)
        if not isfinite(numeric):
            raise ValueError(f"nonfinite Task 9.6 parameter: {item.name}")
        bound = next((boundary for boundary in (item.low, item.high)
                      if boundary is not None
                      and abs(numeric - boundary) <= 4 * ulp(boundary)), None)
        if bound is None or not item.contains(bound):
            raise ValueError(f"Task 9.6 parameter outside frozen bounds: {item.name}")
        canonical[item.name] = bound
        roundoff[item.name] = {"submitted": numeric, "canonical_bound": bound}
    return canonical, roundoff


def evaluate_task9_6_benchmark_v2_candidate(
    *,
    parameters: Mapping[str, float | int],
    evaluation_directory: Path,
    executable: str,
    mode: str,
    corners: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Use only Task 9.5 model-consistent v2 physics, never Task 9 v1."""
    if benchmark_v2_hash() != APPROVED_BENCHMARK_V2_HASH:
        raise RuntimeError("approved corrected Benchmark v2 identity changed")
    if mode not in {"op_only", "hierarchical", "full"}:
        raise ValueError("invalid Task 9.6 evaluation mode")
    frozen = load_experiment_config(FROZEN_TASK7_CONFIG)
    canonical, roundoff = canonicalize_v2_parameters(parameters)
    raw = evaluate_task9_5_v2_candidate(
        base_config=frozen.circuit_config,
        parameters=canonical,
        evaluation_directory=evaluation_directory,
        executable=executable,
        timeout_seconds=frozen.timeout,
        start_frequency_hz=frozen.ngspice_config.start_frequency_hz,
        stop_frequency_hz=frozen.ngspice_config.stop_frequency_hz,
        points_per_decade=frozen.ngspice_config.points_per_decade,
        mode=mode,
        corners=corners,
    )
    feedback = summarize_v2_robust_feedback(raw)
    if feedback["region_semantics"] != V2_SEMANTICS:
        raise RuntimeError("Task 9.6 v2 region semantics mismatch")
    return {
        "schema_version": "task9_6_v2_evaluation_v1",
        "benchmark_v2_hash": APPROVED_BENCHMARK_V2_HASH,
        "parameter_boundary_roundoff": roundoff,
        "raw_v2_result": raw,
        "robust_feedback": feedback,
    }
