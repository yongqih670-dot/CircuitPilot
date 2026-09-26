"""Logged diagnostic PVT witness search; never a formal optimizer comparison."""

from __future__ import annotations

import argparse
import csv
import json
from math import exp, log
from pathlib import Path
import random

from scipy.stats import qmc

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.simulator import resolve_ngspice_executable
from circuitpilot.task9_5_evaluator import evaluate_v2_candidate


ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "research/sky130/two_stage_ota/task7_frozen.yaml"
RANK = ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/history_rank.csv"
STRESS = ("ss__low_v_high_t", "sf__low_v_high_t",
          "fs__low_v_high_t", "ff__high_v_low_t")


def _normal(parameter, value):
    low, high = float(parameter.low), float(parameter.high)
    return ((log(value) - log(low)) / (log(high) - log(low)) if parameter.log
            else (value - low) / (high - low))


def _real(parameter, value):
    low, high = float(parameter.low), float(parameter.high)
    value = min(1.0, max(0.0, value))
    return exp(log(low) + value * (log(high) - log(low))) if parameter.log else low + value * (high - low)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name", default="run_20260926_a")
    parser.add_argument("--seeds", type=int, default=8)
    parser.add_argument("--local", type=int, default=160)
    parser.add_argument("--global-count", type=int, default=40)
    args = parser.parse_args()
    output = ROOT / "research_runs/task9_5_feasibility" / args.run_name
    if output.exists():
        raise FileExistsError(f"refusing to overwrite prior diagnostic run: {output}")
    output.mkdir(parents=True)
    config = load_experiment_config(FROZEN)
    assert config.circuit_config is not None
    executable = resolve_ngspice_executable(config.ngspice_config.executable)
    if executable is None:
        raise FileNotFoundError("ngspice executable unavailable")
    parameters = list(config.search_space)
    rng = random.Random(20260926)
    sobol = qmc.Sobol(d=len(parameters), scramble=True, seed=20260926)
    with RANK.open(encoding="utf-8", newline="") as handle:
        seed_rows = list(csv.DictReader(handle))[:args.seeds]
    seeds = [json.loads(row["parameters"]) for row in seed_rows]
    champions: list[tuple[int, float, dict[str, float]]] = []
    best_stress = float("inf")
    attempts = 0
    promotions = 0

    def record(label, vector, mode, corners=None):
        nonlocal attempts
        attempts += 1
        candidate = {parameter.name: _real(parameter, vector[index])
                     for index, parameter in enumerate(parameters)}
        directory = output / f"attempt_{attempts:04d}_{mode}"
        result = evaluate_v2_candidate(
            base_config=config.circuit_config, parameters=candidate,
            evaluation_directory=directory, executable=executable,
            timeout_seconds=config.timeout,
            start_frequency_hz=config.ngspice_config.start_frequency_hz,
            stop_frequency_hz=config.ngspice_config.stop_frequency_hz,
            points_per_decade=config.ngspice_config.points_per_decade,
            mode=mode, corners=corners,
        )
        item = {"attempt": attempts, "origin": label, "result": result,
                "raw_directory": str(directory.relative_to(ROOT)).replace("\\", "/")}
        with (output / "attempts.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, sort_keys=True, allow_nan=False) + "\n")
        print(json.dumps({"attempt": attempts, "origin": label, "mode": mode,
                          "valid_op": result["op_valid_corner_count"],
                          "score": round(result["op_margin_score"], 3),
                          "feasible": result["is_feasible"]}), flush=True)
        return result

    def promote(label, vector):
        nonlocal promotions
        promotions += 1
        result = record(label, vector, "op_only", corners=None)
        champions.append((result["op_valid_corner_count"],
                          result["op_margin_score"],
                          {parameter.name: _real(parameter, vector[index])
                           for index, parameter in enumerate(parameters)}))
        champions.sort(key=lambda row: (-row[0], row[1]))
        del champions[12:]
        if result["op_valid_corner_count"] == 15 and result["first_failure"] is None:
            full = record(label + ":verification", vector, "full")
            if full["is_feasible"]:
                (output / "witness.json").write_text(
                    json.dumps(full, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                return True
        return False

    for index, seed in enumerate(seeds):
        vector = [_normal(parameter, seed[parameter.name]) for parameter in parameters]
        if promote(f"historical_seed_{index}", vector):
            return

    total = args.local + args.global_count
    for index in range(total):
        if index < args.local:
            if not champions:
                break
            pool = champions[:min(4, len(champions))]
            parent = pool[index % len(pool)][2]
            vector = [_normal(parameter, parent[parameter.name]) for parameter in parameters]
            for dimension in rng.sample(range(len(vector)), rng.choice((1, 2, 3))):
                vector[dimension] = min(1.0, max(0.0, vector[dimension]
                                      + rng.gauss(0.0, rng.choice((0.06, 0.12, 0.24)))))
            label = f"local_{index:03d}"
        else:
            vector = sobol.random(1)[0].tolist()
            label = f"sobol_{index - args.local:03d}"
        stress = record(label, vector, "op_only", corners=STRESS)
        score = stress["op_margin_score"]
        best_stress = min(best_stress, score)
        if (stress["op_valid_corner_count"] == 4 or
                score <= best_stress + 0.5 or index % 5 == 0):
            if promote(label + ":promoted", vector):
                return
    (output / "search_summary.json").write_text(json.dumps({
        "witness_found": False, "attempts": attempts, "promotions": promotions,
        "best_op_valid_corners": champions[0][0] if champions else 0,
        "best_op_score": champions[0][1] if champions else None,
        "best_parameters": champions[0][2] if champions else None,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
