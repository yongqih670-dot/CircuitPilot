"""Read-only machine preflight; exit nonzero while Task 10 is blocked."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from circuitpilot.task10_execution_guard import (
    DEFAULT_GATE, check_task10_execution_guard,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path, default=DEFAULT_GATE)
    args = parser.parse_args()
    decision = check_task10_execution_guard(args.gate)
    print(json.dumps(decision.to_dict(), indent=2, sort_keys=True))
    return 0 if decision.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())
