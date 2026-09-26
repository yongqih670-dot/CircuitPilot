"""Fresh complete negative Full-PVT characterization of best in-bounds candidate."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from circuitpilot.environment_fingerprint import collect_environment_fingerprint
from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.simulator import resolve_ngspice_executable
from circuitpilot.task9_5_evaluator import evaluate_v2_candidate


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research_runs/task9_5_full_characterization"
REPORT = ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/full_characterization_summary.json"
PARAMETERS = ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/refinement_analysis.json"


def main() -> None:
    if OUTPUT.exists() or REPORT.exists():
        raise FileExistsError("refusing to overwrite a Full-PVT diagnostic")
    config = load_experiment_config(ROOT / "research/sky130/two_stage_ota/task7_frozen.yaml")
    executable = resolve_ngspice_executable(config.ngspice_config.executable)
    if executable is None:
        raise FileNotFoundError("ngspice unavailable")
    parameters = json.loads(PARAMETERS.read_text(encoding="utf-8"))["best_parameters"]
    result = evaluate_v2_candidate(
        base_config=config.circuit_config, parameters=parameters,
        evaluation_directory=OUTPUT / "raw", executable=executable,
        timeout_seconds=config.timeout,
        start_frequency_hz=config.ngspice_config.start_frequency_hz,
        stop_frequency_hz=config.ngspice_config.stop_frequency_hz,
        points_per_decade=config.ngspice_config.points_per_decade,
        mode="full",
    )
    failures = Counter()
    passing = 0
    for corner in result["corners"]:
        passing += all(value == 0 for value in corner["constraint_components"].values())
        failures.update({name: 1 for name, value in corner["constraint_components"].items()
                         if value > 0})
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result_path = OUTPUT / "full_matrix.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True,
                                      allow_nan=False) + "\n", encoding="utf-8")
    summary = {
        "benchmark_v2_hash": result["benchmark_v2_hash"],
        "is_feasible": result["is_feasible"],
        "complete_full_matrix": result["complete_full_matrix"],
        "process_calls": result["process_calls"],
        "accumulated_ngspice_seconds": result["accumulated_ngspice_seconds"],
        "passing_corners_all_constraints": passing,
        "constraint_failure_corner_counts": dict(failures),
        "first_failure": result["first_failure"],
        "all_vdd_and_temperature_checks_passed": all(
            all(corner["application_checks"].values()) for corner in result["corners"]
        ),
        "full_matrix_sha256": sha256(result_path.read_bytes()).hexdigest(),
        "raw_directory": str((OUTPUT / "raw").relative_to(ROOT)).replace("\\", "/"),
        "environment_fingerprint": collect_environment_fingerprint(executable),
    }
    REPORT.write_text(json.dumps(summary, indent=2, sort_keys=True,
                                 allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items()
                      if key != "environment_fingerprint"}, indent=2))


if __name__ == "__main__":
    main()
