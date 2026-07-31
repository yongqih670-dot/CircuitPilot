from math import sqrt

import pytest

from circuitpilot.analysis import find_cutoff_frequency, find_highpass_cutoff_frequency
from circuitpilot.exceptions import AnalysisError


def test_find_cutoff_frequency_returns_exact_sample() -> None:
    cutoff = find_cutoff_frequency((10.0, 100.0, 1_000.0), (0.0, -3.0, -20.0))

    assert cutoff == pytest.approx(100.0)


def test_find_cutoff_frequency_interpolates_on_log_frequency() -> None:
    cutoff = find_cutoff_frequency((100.0, 1_000.0), (0.0, -6.0))

    assert cutoff == pytest.approx(sqrt(100.0 * 1_000.0))


def test_find_cutoff_frequency_uses_post_peak_crossing() -> None:
    cutoff = find_cutoff_frequency(
        (10.0, 100.0, 1_000.0, 10_000.0), (-1.0, 1.0, -2.0, -20.0)
    )

    assert cutoff == pytest.approx(1_000.0)


def test_find_highpass_cutoff_frequency_returns_rising_crossing() -> None:
    cutoff = find_highpass_cutoff_frequency(
        (10.0, 100.0, 1_000.0), (-20.0, -3.0, 0.0)
    )

    assert cutoff == pytest.approx(100.0)


def test_find_highpass_cutoff_frequency_interpolates_on_log_frequency() -> None:
    cutoff = find_highpass_cutoff_frequency((100.0, 1_000.0), (-6.0, 0.0))

    assert cutoff == pytest.approx(sqrt(100.0 * 1_000.0))


def test_find_highpass_cutoff_frequency_requires_covered_crossing() -> None:
    with pytest.raises(AnalysisError, match="decrease the AC start frequency"):
        find_highpass_cutoff_frequency((100.0, 1_000.0), (-1.0, 0.0))


@pytest.mark.parametrize(
    "frequencies, gains, message",
    [
        ((10.0,), (0.0,), "at least two"),
        ((10.0, 100.0), (0.0,), "equal lengths"),
        ((10.0, 10.0), (0.0, -3.0), "increasing"),
        ((10.0, 100.0), (0.0, -1.0), "no -3 dB crossing"),
    ],
)
def test_find_cutoff_frequency_rejects_invalid_or_incomplete_data(
    frequencies: tuple[float, ...], gains: tuple[float, ...], message: str
) -> None:
    with pytest.raises(AnalysisError, match=message):
        find_cutoff_frequency(frequencies, gains)
