"""Run a frozen Task 6 suite with cell-level resume."""

from __future__ import annotations

import argparse
from pathlib import Path

from circuitpilot.experiments.task6_batch import DESIGNS, run_task6_suite


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design", required=True, choices=tuple(DESIGNS))
    parser.add_argument(
        "--base-config", type=Path,
        default=Path(
            "research/sky130/differential_amplifier/"
            "differential_amplifier_frozen.yaml"
        ),
    )
    parser.add_argument(
        "--output-root", type=Path, default=Path("research_runs/task6")
    )
    parser.add_argument("--resume-suite", type=Path)
    args = parser.parse_args()
    suite = run_task6_suite(
        base_config_path=args.base_config, design=args.design,
        output_root=args.output_root, resume_suite=args.resume_suite,
    )
    print(suite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
