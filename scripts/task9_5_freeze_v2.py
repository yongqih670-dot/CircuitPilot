"""Write the additive semantics-only Benchmark v2 diagnostic identity."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from circuitpilot.task9_5_benchmark import benchmark_v2_definition, benchmark_v2_hash  # noqa: E402


def main() -> None:
    output = ROOT / "research/sky130/two_stage_ota/task9_5/benchmark_v2_manifest.json"
    payload = {"benchmark_v2_hash": benchmark_v2_hash(),
               "definition": benchmark_v2_definition()}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(payload["benchmark_v2_hash"])


if __name__ == "__main__":
    main()
