"""Command-line entry point for Task 8 smoke and formal suites."""

from __future__ import annotations

import argparse
from pathlib import Path

from circuitpilot.experiments.task8_batch import run_task8_suite


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task7_frozen.yaml"
)
TASK8_RESULTS = (
    PROJECT_ROOT
    / "research"
    / "sky130"
    / "two_stage_ota"
    / "task8"
    / "results"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "design",
        choices=("smoke", "equal_candidate", "equal_simulation_time"),
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--methods", nargs="+")
    parser.add_argument("--seeds", nargs="+", type=int)
    args = parser.parse_args()
    output = args.output or (TASK8_RESULTS / args.design)
    suite = run_task8_suite(
        base_config_path=args.config,
        design=args.design,
        output_root=output,
        workers=args.workers,
        methods=("random", "de", "tpe", "bo") if args.methods is None else args.methods,
        seeds=args.seeds,
    )
    print(suite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
