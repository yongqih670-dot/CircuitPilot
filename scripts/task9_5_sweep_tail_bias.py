"""Out-of-benchmark fixed-tail-bias bottleneck diagnostic only."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.simulator import resolve_ngspice_executable
from circuitpilot.task9_5_evaluator import evaluate_v2_candidate


ROOT = Path(__file__).resolve().parents[1]
PARAMETERS = ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/refinement_analysis.json"
OUTPUT = ROOT / "research_runs/task9_5_feasibility/tail_bias_diagnostic_20260926_c"
VALUES = (0.60, 0.64, 0.68, 0.72, 0.76, 0.80, 0.84)


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing overwrite: {OUTPUT}")
    OUTPUT.mkdir(parents=True)
    config = load_experiment_config(ROOT / "research/sky130/two_stage_ota/task7_frozen.yaml")
    executable = resolve_ngspice_executable(config.ngspice_config.executable)
    if executable is None:
        raise FileNotFoundError("ngspice unavailable")
    parameters = json.loads(PARAMETERS.read_text(encoding="utf-8"))["best_parameters"]
    for index, tail_bias in enumerate(VALUES, 1):
        result = evaluate_v2_candidate(
            base_config=replace(config.circuit_config, tail_bias_v=tail_bias),
            parameters=parameters,
            evaluation_directory=OUTPUT / f"attempt_{index:02d}_tail_{tail_bias:.2f}",
            executable=executable, timeout_seconds=config.timeout,
            start_frequency_hz=config.ngspice_config.start_frequency_hz,
            stop_frequency_hz=config.ngspice_config.stop_frequency_hz,
            points_per_decade=config.ngspice_config.points_per_decade,
            mode="op_only", corners=None,
        )
        passing = sum(all(value == 0 for value in corner["constraint_components"].values())
                      for corner in result["corners"])
        with (OUTPUT / "attempts.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"attempt": index, "tail_bias_v": tail_bias,
                                     "outside_benchmark": tail_bias != 0.72,
                                     "result": result},
                                    sort_keys=True, allow_nan=False) + "\n")
        print(json.dumps({"tail_bias_v": tail_bias, "op_passing": passing,
                          "region_passing": result["op_valid_corner_count"],
                          "op_score": result["op_margin_score"]}), flush=True)
    ledger = OUTPUT / "attempts.jsonl"
    print("ledger_sha256", sha256(ledger.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
