"""Generate and execute the pre-registered Task 6 paired cost pilot."""

from __future__ import annotations

import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path
from statistics import fmean, median
from time import monotonic
from typing import Any, Sequence

import numpy as np

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.experiments.optimizers.base import SearchSpaceCodec
from circuitpilot.experiments.simulation import (
    Sky130DifferentialAmplifierNgspiceSimulator,
)
from circuitpilot.run_directory import prepare_research_run_directory
from circuitpilot.sky130_differential_amplifier import (
    Sky130DifferentialAmplifierCircuitConfig,
)
from circuitpilot.task6_physics import (
    classify_task6_physics,
    run_task6_op_only,
)


TASK5_HASH = "57d2183621ecf37e5ca22e012452c43fce6459be7d347a5cfc93d0b394c14378"
PILOT_SEED = 6001
PILOT_COUNT = 32
PROTOCOL_VERSION = "task6_cost_profile_paired_v1"


def _canonical_candidates(candidates: list[dict[str, Any]]) -> bytes:
    return json.dumps(
        candidates, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def generate_candidates(config_path: Path, destination: Path) -> Path:
    config = load_experiment_config(config_path)
    if config.computed_benchmark_hash() != TASK5_HASH:
        raise ValueError("pilot requires the frozen Task 5 benchmark hash")
    codec = SearchSpaceCodec(config)
    rng = np.random.default_rng(PILOT_SEED)
    candidates = [codec.sample(rng) for _ in range(PILOT_COUNT)]
    design_hash = sha256(_canonical_candidates(candidates)).hexdigest()
    payload = {
        "protocol_version": PROTOCOL_VERSION,
        "task5_benchmark_hash": TASK5_HASH,
        "numpy_generator": "default_rng",
        "seed": PILOT_SEED,
        "candidate_count": PILOT_COUNT,
        "candidate_design_sha256": design_hash,
        "candidates": candidates,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return destination


def _load_candidates(path: Path) -> tuple[list[dict[str, Any]], str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    candidates = payload["candidates"]
    expected = sha256(_canonical_candidates(candidates)).hexdigest()
    if (
        payload.get("protocol_version") != PROTOCOL_VERSION
        or payload.get("task5_benchmark_hash") != TASK5_HASH
        or payload.get("seed") != PILOT_SEED
        or payload.get("candidate_count") != PILOT_COUNT
        or payload.get("candidate_design_sha256") != expected
        or len(candidates) != PILOT_COUNT
    ):
        raise ValueError("pilot candidate design does not match its pre-registration")
    return candidates, expected


def _distribution(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "mean": fmean(values),
        "median": median(values),
        "minimum": min(values),
        "q1": float(np.quantile(array, 0.25)),
        "q3": float(np.quantile(array, 0.75)),
        "maximum": max(values),
    }


def run_pilot(
    config_path: Path,
    candidates_path: Path,
    output_root: Path,
) -> Path:
    config = load_experiment_config(config_path)
    if config.computed_benchmark_hash() != TASK5_HASH:
        raise ValueError("pilot requires the frozen Task 5 benchmark hash")
    circuit = config.circuit_config
    if not isinstance(circuit, Sky130DifferentialAmplifierCircuitConfig):
        raise ValueError("pilot requires the frozen differential circuit")
    candidates, design_hash = _load_candidates(candidates_path)
    run = prepare_research_run_directory(
        None,
        default_root=output_root,
        configuration_sha256=sha256(
            (TASK5_HASH + design_hash + PROTOCOL_VERSION).encode("ascii")
        ).hexdigest(),
    )
    full_simulator = Sky130DifferentialAmplifierNgspiceSimulator(config)
    rows: list[dict[str, Any]] = []
    for index, parameters in enumerate(candidates):
        candidate_directory = run.path / f"candidate_{index:03d}"
        order = ("full", "op_only") if index % 2 == 0 else ("op_only", "full")
        results: dict[str, Any] = {}
        for mode in order:
            started = monotonic()
            if mode == "full":
                launches: list[int] = []
                simulation = full_simulator.evaluate(
                    parameters,
                    candidate_directory / "full",
                    lambda: launches.append(1),
                )
                results["full_runtime_seconds"] = monotonic() - started
                results["full_process_seconds"] = simulation.process.elapsed_seconds
                results["full_process_calls"] = len(launches)
            else:
                op_only = run_task6_op_only(
                    circuit,
                    parameters,
                    candidate_directory / "op_only",
                    executable=config.ngspice_config.executable,
                    timeout_seconds=config.timeout,
                )
                assessment = classify_task6_physics(op_only.operating_point)
                results["op_only_runtime_seconds"] = monotonic() - started
                results["op_only_process_seconds"] = op_only.process.elapsed_seconds
                results["physics_status"] = assessment.physics_status
                results["physics_violation_mask"] = assessment.violation_mask
                results["physics_violation_count"] = assessment.violation_count
                results["physics_violation_types"] = list(
                    assessment.violation_types
                )
                results["op_constraint_violation"] = (
                    assessment.op_constraint_violation
                )
                results["output_dc_voltage"] = (
                    op_only.operating_point.output_voltage_v
                )
        rows.append(
            {
                "candidate_index": index,
                "execution_order": "->".join(order),
                "parameters": json.dumps(
                    parameters, sort_keys=True, separators=(",", ":")
                ),
                **results,
            }
        )
        _write_rows(run.path / "pilot_raw.csv", rows)

    op_values = [float(row["op_only_runtime_seconds"]) for row in rows]
    full_values = [float(row["full_runtime_seconds"]) for row in rows]
    ratios = [op / full for op, full in zip(op_values, full_values)]
    summary = {
        "run_id": run.run_id,
        "protocol_version": PROTOCOL_VERSION,
        "task5_benchmark_hash": TASK5_HASH,
        "candidate_count": len(rows),
        "candidate_design_sha256": design_hash,
        "op_only_runtime_seconds": _distribution(op_values),
        "full_runtime_seconds": _distribution(full_values),
        "paired_op_to_full_ratio": _distribution(ratios),
        "op_valid_count": sum(row["physics_status"] == "valid" for row in rows),
        "op_invalid_count": sum(
            row["physics_status"] == "invalid" for row in rows
        ),
        "process_failures": 0,
    }
    (run.path / "pilot_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return run.path


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    columns = (
        "candidate_index",
        "execution_order",
        "parameters",
        "physics_status",
        "physics_violation_mask",
        "physics_violation_count",
        "physics_violation_types",
        "op_constraint_violation",
        "output_dc_voltage",
        "op_only_runtime_seconds",
        "op_only_process_seconds",
        "full_runtime_seconds",
        "full_process_seconds",
        "full_process_calls",
    )
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            serialized = dict(row)
            serialized["physics_violation_types"] = json.dumps(
                row["physics_violation_types"], separators=(",", ":")
            )
            writer.writerow(serialized)
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(
            "research/sky130/differential_amplifier/"
            "differential_amplifier_frozen.yaml"
        ),
    )
    parser.add_argument(
        "--candidates",
        type=Path,
        default=Path(
            "research/sky130/differential_amplifier/task6/"
            "pilot_candidates.json"
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("research_runs/task6_cost_profile"),
    )
    parser.add_argument(
        "--generate-only",
        action="store_true",
        help="write the pre-simulation candidate design without running ngspice",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.generate_only:
        path = generate_candidates(args.config, args.candidates)
        print(f"Pilot candidates: {path.resolve()}")
    else:
        path = run_pilot(args.config, args.candidates, args.output_root)
        print(f"Pilot output: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
