"""Publish losslessly compressed diagnostic ledgers without raw run trees."""

from __future__ import annotations

import gzip
from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "research_runs/task9_5_feasibility"
TARGET = ROOT / "research/sky130/two_stage_ota/task9_5/feasibility"
RUNS = {
    "initial": "run_20260926_a",
    "refinement": "refine_20260926_b",
    "tail_bias_diagnostic": "tail_bias_diagnostic_20260926_c",
}


def main() -> None:
    manifests = []
    for label, directory in RUNS.items():
        source = SOURCE / directory / "attempts.jsonl"
        target = TARGET / f"{label}_attempts.jsonl.gz"
        if target.exists():
            raise FileExistsError(f"refusing overwrite: {target}")
        content = source.read_bytes()
        with target.open("wb") as handle:
            with gzip.GzipFile(filename="", mode="wb", fileobj=handle,
                               compresslevel=9, mtime=0) as compressed:
                compressed.write(content)
        with gzip.open(target, "rb") as handle:
            assert handle.read() == content
        manifests.append({
            "run": directory,
            "raw_ledger_sha256": sha256(content).hexdigest(),
            "raw_ledger_bytes": len(content),
            "compressed_ledger": str(target.relative_to(ROOT)).replace("\\", "/"),
            "compressed_sha256": sha256(target.read_bytes()).hexdigest(),
            "compressed_bytes": target.stat().st_size,
            "attempts": len(content.splitlines()),
        })
    (TARGET / "diagnostic_ledger_manifest.json").write_text(
        json.dumps(manifests, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifests, indent=2))


if __name__ == "__main__":
    main()
