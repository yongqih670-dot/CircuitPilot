"""Freeze the 48 proposal parameters; do not run SPICE."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from circuitpilot.experiments.config import load_experiment_config
from circuitpilot.task9_6_sensitivity import generate_local_sensitivity_candidates
from circuitpilot.task9_6_v2_evaluator import canonicalize_v2_parameters


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "research/sky130/two_stage_ota/task9_5/feasibility/refinement_analysis.json"
NEAR = ROOT / "research/sky130/two_stage_ota/task9_6/near_corner_selection.json"
OUTPUT = ROOT / "research/sky130/two_stage_ota/task9_6/sensitivity_candidates.json"


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing overwrite: {OUTPUT}")
    frozen = load_experiment_config(ROOT / "research/sky130/two_stage_ota/task7_frozen.yaml")
    original = json.loads(BASELINE.read_text(encoding="utf-8"))["best_parameters"]
    canonical, boundary_roundoff = canonicalize_v2_parameters(original)
    corners = json.loads(NEAR.read_text(encoding="utf-8"))["selected_corner_ids"]
    rows = generate_local_sensitivity_candidates(canonical, frozen.search_space)
    payload = {
        "schema_version": "task9_6_sensitivity_candidates_v1",
        "benchmark_v2_hash": "8f622a92370e33ea6f608d7a31077096b8188b868dc070cebbf3ce67f9059708",
        "source_baseline_sha256": sha256(BASELINE.read_bytes()).hexdigest(),
        "baseline_parameter_boundary_roundoff": boundary_roundoff,
        "baseline_parameters": canonical,
        "corner_ids": corners,
        "candidate_count": len(rows),
        "candidates": rows,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(f"frozen {len(rows)} distinct in-bounds candidates over {len(corners)} corners")


if __name__ == "__main__":
    main()
