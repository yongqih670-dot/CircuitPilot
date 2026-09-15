"""Measure a model-free ngspice launch lower bound for Task 7 cost interpretation."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean, median, quantiles
import sys
from tempfile import TemporaryDirectory
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from circuitpilot.simulator import run_ngspice


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/sky130/two_stage_ota/results/cost_profile"),
    )
    args = parser.parse_args()
    if args.repetitions <= 0:
        parser.error("--repetitions must be positive")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    with TemporaryDirectory(prefix="circuitpilot-task7-bare-") as temporary:
        temporary_root = Path(temporary)
        for index in range(args.repetitions):
            run = temporary_root / f"bare_process_{index + 1:03d}"
            run.mkdir()
            netlist = run / "bare.cir"
            netlist.write_text(
                "* Task 7 model-free process baseline\n"
                "V1 out 0 0\n"
                ".control\nop\nquit\n.endc\n.end\n",
                encoding="utf-8",
            )
            started = monotonic()
            result = run_ngspice(netlist, log_path=run / "ngspice.log")
            rows.append(
                {
                    "repetition": index + 1,
                    "process_elapsed_seconds": result.elapsed_seconds,
                    "outer_elapsed_seconds": monotonic() - started,
                }
            )
    with (output / "bare_process_runtime.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {"repetitions": len(rows)}
    for field in ("process_elapsed_seconds", "outer_elapsed_seconds"):
        values = [float(row[field]) for row in rows]
        q1, _, q3 = quantiles(values, n=4, method="inclusive")
        summary[field] = {
            "mean": mean(values),
            "median": median(values),
            "q1": q1,
            "q3": q3,
            "iqr": q3 - q1,
            "minimum": min(values),
            "maximum": max(values),
        }
    summary["interpretation"] = (
        "Model-free ngspice launch lower bound only; the gap to Task 7 analysis "
        "runtime combines SKY130 model loading and solver work."
    )
    (output / "bare_process_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
