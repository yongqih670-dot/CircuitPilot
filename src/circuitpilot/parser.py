"""Parsing of column-oriented AC analysis data written by ngspice."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import re

from circuitpilot.exceptions import ParseError


@dataclass(frozen=True, slots=True)
class ACAnalysisResult:
    """Frequency-domain response returned by an ngspice AC analysis."""

    frequency_hz: tuple[float, ...]
    gain_db: tuple[float, ...]
    phase_deg: tuple[float, ...]

    def __len__(self) -> int:
        """Return the number of frequency samples."""
        return len(self.frequency_hz)


_COLUMN_SEPARATOR = re.compile(r"[\s,]+")


def _parse_number(token: str) -> float:
    """Parse a number, accepting Fortran-style ``D`` exponents."""
    return float(token.replace("D", "E").replace("d", "e"))


def parse_ac_output(output_path: str | Path) -> ACAnalysisResult:
    """Parse frequency, gain, and phase columns from ngspice ``wrdata`` output.

    Header lines and comments beginning with ``#`` or ``*`` are ignored. Each
    data line must contain exactly the first three relevant numeric columns:
    frequency in hertz, gain in decibels, and phase in degrees.

    Args:
        output_path: Text data file produced by the generated netlist.

    Returns:
        Immutable tuples of frequency, gain, and phase samples.

    Raises:
        ParseError: If the file cannot be read or contains invalid data.
    """
    source = Path(output_path).resolve()
    try:
        lines = source.read_text(encoding="utf-8", errors="strict").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ParseError(f"failed to read AC output '{source}': {exc}") from exc

    frequencies: list[float] = []
    gains: list[float] = []
    phases: list[float] = []

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith(("#", "*")):
            continue

        tokens = [token for token in _COLUMN_SEPARATOR.split(line) if token]
        if not tokens:
            continue
        try:
            values = [_parse_number(token) for token in tokens]
        except ValueError:
            numeric_token_count = 0
            for token in tokens:
                try:
                    _parse_number(token)
                except ValueError:
                    continue
                numeric_token_count += 1
            if not frequencies and numeric_token_count == 0:
                continue
            raise ParseError(
                f"invalid numeric data at line {line_number}: {raw_line!r}"
            ) from None

        if len(values) != 3:
            raise ParseError(
                f"expected 3 columns at line {line_number}, found {len(values)}"
            )
        frequency, gain, phase = values
        if not all(isfinite(value) for value in values):
            raise ParseError(f"non-finite value at line {line_number}")
        if frequency <= 0:
            raise ParseError(f"frequency must be positive at line {line_number}")
        if frequencies and frequency <= frequencies[-1]:
            raise ParseError(
                f"frequencies must be strictly increasing at line {line_number}"
            )
        frequencies.append(frequency)
        gains.append(gain)
        phases.append(phase)

    if not frequencies:
        raise ParseError(f"AC output contains no data rows: '{source}'")

    return ACAnalysisResult(
        frequency_hz=tuple(frequencies),
        gain_db=tuple(gains),
        phase_deg=tuple(phases),
    )
