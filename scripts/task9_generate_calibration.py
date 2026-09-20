"""Generate the pre-registered independent Task 9 Sobol calibration set."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import scipy
from scipy.stats import qmc


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from circuitpilot.task7_protocol import (  # noqa: E402
    SEARCH_DIMENSIONS,
    TASK7_SEARCH_SPACE_HASH,
    decode_unit_candidate,
    stable_hash,
)


OUTPUT = (
    PROJECT_ROOT
    / "research"
    / "sky130"
    / "two_stage_ota"
    / "task9"
    / "calibration"
    / "calibration_candidates.json"
)
SEED = 9200901
M = 6


def main() -> int:
    sampler = qmc.Sobol(d=len(SEARCH_DIMENSIONS), scramble=True, seed=SEED)
    coordinates = sampler.random_base2(m=M)
    designs = []
    decoded_keys: set[str] = set()
    for index, row in enumerate(coordinates):
        unit = [float(value) for value in row]
        parameters = decode_unit_candidate(unit)
        key = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        if key in decoded_keys:
            raise RuntimeError("decoded Sobol candidate is duplicated")
        decoded_keys.add(key)
        designs.append(
            {
                "design_id": f"sobol_{index:03d}",
                "unit_coordinates": unit,
                "parameters": parameters,
                "sources": [
                    {
                        "generator": "scipy.stats.qmc.Sobol",
                        "index": index,
                        "seed": SEED,
                    }
                ],
            }
        )
    identity = [
        {
            "design_id": design["design_id"],
            "unit_coordinates": design["unit_coordinates"],
            "parameters": design["parameters"],
        }
        for design in designs
    ]
    payload = {
        "schema_version": "task9_sobol_calibration_candidates_v1",
        "generator": "scipy.stats.qmc.Sobol",
        "scipy_version": scipy.__version__,
        "dimensions": len(SEARCH_DIMENSIONS),
        "scramble": True,
        "seed": SEED,
        "random_base2_m": M,
        "candidate_count": len(designs),
        "task7_search_space_hash": TASK7_SEARCH_SPACE_HASH,
        "search_dimensions": [list(item) for item in SEARCH_DIMENSIONS],
        "candidate_set_hash": stable_hash(identity),
        "designs": designs,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: payload[key] for key in ("candidate_count", "candidate_set_hash", "scipy_version")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
