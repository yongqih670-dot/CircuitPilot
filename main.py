"""Source-checkout entry point for ``python main.py --config ...``."""

from pathlib import Path
import sys


SOURCE_DIRECTORY = Path(__file__).resolve().parent / "src"
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from circuitpilot.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

