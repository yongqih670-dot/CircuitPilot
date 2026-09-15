"""CLI for the frozen Task 7 smoke and formal suites."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from circuitpilot.experiments.task7_batch import run_task7_suite


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("design", choices=("smoke", "formal"))
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("research/sky130/two_stage_ota/task7_frozen.yaml"),
    )
    parser.add_argument(
        "--output-root", type=Path, default=Path("research_runs/task7")
    )
    parser.add_argument("--resume-suite", type=Path)
    parser.add_argument("--methods", nargs="+", choices=("random", "de", "tpe", "bo"))
    parser.add_argument("--seeds", nargs="+", type=int)
    args = parser.parse_args()
    suite = run_task7_suite(
        base_config_path=args.config,
        design=args.design,
        output_root=args.output_root,
        resume_suite=args.resume_suite,
        methods=("random", "de", "tpe", "bo") if args.methods is None else args.methods,
        seeds=args.seeds,
    )
    print(suite)


if __name__ == "__main__":
    main()
