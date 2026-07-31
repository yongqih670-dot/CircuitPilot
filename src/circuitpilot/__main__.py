"""Allow ``python -m circuitpilot`` execution."""

from circuitpilot.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

