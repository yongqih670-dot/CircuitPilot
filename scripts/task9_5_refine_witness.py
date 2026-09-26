"""Pre-registered coordinate refinement around best original-bound OP result."""

from __future__ import annotations

import json
from math import exp, log
from pathlib import Path

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.simulator import resolve_ngspice_executable
from circuitpilot.task9_5_evaluator import evaluate_v2_candidate


ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "research/sky130/two_stage_ota/task7_frozen.yaml"
SOURCE = ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/search_analysis.json"
OUTPUT = ROOT / "research_runs/task9_5_feasibility/refine_20260926_b"
STRESS = ("ss__nominal", "ss__high_v_low_t", "fs__nominal",
          "fs__high_v_low_t", "ss__low_v_high_t", "fs__low_v_high_t")


def normalized(parameter, value):
    low, high = parameter.low, parameter.high
    return ((log(value) - log(low)) / (log(high) - log(low)) if parameter.log
            else (value - low) / (high - low))


def real(parameter, value):
    value = min(1.0, max(0.0, value))
    low, high = parameter.low, parameter.high
    return exp(log(low) + value * (log(high) - log(low))) if parameter.log else low + value * (high - low)


def passing(result):
    return sum(corner["constraint_components"] is not None
               and all(value == 0 for value in corner["constraint_components"].values())
               and not corner["analysis_errors"].get("op")
               for corner in result["corners"])


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing overwrite: {OUTPUT}")
    OUTPUT.mkdir(parents=True)
    config = load_experiment_config(FROZEN)
    executable = resolve_ngspice_executable(config.ngspice_config.executable)
    if executable is None:
        raise FileNotFoundError("ngspice unavailable")
    parameters = list(config.search_space)
    initial = json.loads(SOURCE.read_text(encoding="utf-8"))["best_parameters"]
    champion = [normalized(parameter, initial[parameter.name]) for parameter in parameters]
    champion_passing = 11
    champion_score = float("inf")
    attempts = 0

    def evaluate(vector, label, corners=STRESS, mode="op_only"):
        nonlocal attempts
        attempts += 1
        candidate = {parameter.name: real(parameter, vector[index])
                     for index, parameter in enumerate(parameters)}
        directory = OUTPUT / f"attempt_{attempts:04d}_{mode}"
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
        with (OUTPUT / "attempts.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, sort_keys=True, allow_nan=False) + "\n")
        print(json.dumps({"attempt": attempts, "origin": label,
                          "corners": len(corners) if corners else 15,
                          "op_passing": passing(result),
                          "score": round(result["op_margin_score"], 4),
                          "full_feasible": result["is_feasible"]}), flush=True)
        return result

    baseline = evaluate(champion, "baseline_fresh", corners=None)
    champion_passing = passing(baseline)
    champion_score = baseline["op_margin_score"]
    dimensions = [index for index, parameter in enumerate(parameters)
                  if parameter.name != "compensation_capacitance_f"]
    for round_index in range(3):
        proposals = []
        for dimension in dimensions:
            for shift in (-0.15, -0.06, 0.06, 0.15):
                vector = list(champion)
                vector[dimension] = min(1.0, max(0.0, vector[dimension] + shift))
                label = f"r{round_index}_d{dimension}_s{shift:+.2f}"
                result = evaluate(vector, label)
                proposals.append((result["op_margin_score"], vector, label))
        proposals.sort(key=lambda row: row[0])
        selected = proposals[:8]
        remaining = proposals[8:]
        selected.extend(remaining[index * len(remaining) // 4]
                        for index in range(4))
        for _, vector, label in selected:
            result = evaluate(vector, label + ":promoted", corners=None)
            count = passing(result)
            score = result["op_margin_score"]
            if (count, -score) > (champion_passing, -champion_score):
                champion = vector
                champion_passing = count
                champion_score = score
            if count == 15 and result["first_failure"] is None:
                full = evaluate(vector, label + ":verification", corners=None,
                                mode="full")
                if full["is_feasible"]:
                    (OUTPUT / "witness.json").write_text(
                        json.dumps(full, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
                    return
        print(f"round {round_index} champion {champion_passing}/15 score {champion_score:.4f}",
              flush=True)
    (OUTPUT / "search_summary.json").write_text(json.dumps({
        "witness_found": False, "attempts": attempts,
        "best_op_passing_corners": champion_passing,
        "best_op_score": champion_score,
        "best_parameters": {parameter.name: real(parameter, champion[index])
                            for index, parameter in enumerate(parameters)},
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
