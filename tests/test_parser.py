from pathlib import Path

import pytest

from circuitpilot.exceptions import ParseError
from circuitpilot.parser import parse_ac_output


def test_parse_ac_output_reads_ngspice_columns(tmp_path: Path) -> None:
    output = tmp_path / "ac.dat"
    output.write_text(
        "frequency vdb(out) vp(out)\n"
        "1.00000000e+01  -4.3429e-04  -5.7290e-01\n"
        "1.00000000D+02  -4.3214e-02  -5.7106e+00\n"
        "1.00000000e+03  -3.0103e+00  -4.5000e+01\n",
        encoding="utf-8",
    )

    result = parse_ac_output(output)

    assert result.frequency_hz == (10.0, 100.0, 1000.0)
    assert result.gain_db[-1] == pytest.approx(-3.0103)
    assert result.phase_deg[-1] == pytest.approx(-45.0)


def test_parse_ac_output_accepts_comments_blanks_and_commas(tmp_path: Path) -> None:
    output = tmp_path / "ac.dat"
    output.write_text("# generated\n\n10, -0.1, -1\n20, -0.2, -2\n", encoding="utf-8")

    result = parse_ac_output(output)

    assert len(result) == 2


@pytest.mark.parametrize(
    "contents, expected_message",
    [
        ("frequency gain phase\n", "no data rows"),
        ("10 -0.1\n", "expected 3 columns"),
        ("10 -0.1 -1\n5 -0.2 -2\n", "strictly increasing"),
        ("0 -0.1 -1\n", "must be positive"),
        ("10 NaN -1\n", "non-finite"),
        ("10 broken -1\n", "invalid numeric data"),
    ],
)
def test_parse_ac_output_rejects_bad_data(
    tmp_path: Path, contents: str, expected_message: str
) -> None:
    output = tmp_path / "bad.dat"
    output.write_text(contents, encoding="utf-8")

    with pytest.raises(ParseError, match=expected_message):
        parse_ac_output(output)


def test_parse_ac_output_wraps_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ParseError, match="failed to read"):
        parse_ac_output(tmp_path / "missing.dat")

