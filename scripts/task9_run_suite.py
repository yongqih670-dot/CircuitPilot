"""Run or resume one frozen Task 9 experiment suite."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from circuitpilot.experiments.task9_batch import run_task9_suite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", choices=("smoke", "equal_candidate", "equal_simulation_time"), required=True)
    parser.add_argument("--config", type=Path, default=PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task7_frozen.yaml")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--methods", nargs="*", choices=("random", "de", "tpe", "bo"))
    parser.add_argument("--seeds", nargs="*", type=int)
    args = parser.parse_args()
    run_task9_suite(
        base_config_path=args.config,
        design=args.design,
        output_root=args.output,
        methods=("random", "de", "tpe", "bo") if not args.methods else tuple(args.methods),
        seeds=None if args.seeds is None else tuple(args.seeds),
        workers=args.workers,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
