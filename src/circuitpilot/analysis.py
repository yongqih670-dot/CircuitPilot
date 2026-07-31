"""Measurements derived from simulated AC response data."""

from __future__ import annotations

from math import isfinite, log10
from typing import Sequence

from circuitpilot.exceptions import AnalysisError


def _validate_response(
    frequency_hz: Sequence[float],
    gain_db: Sequence[float],
    drop_db: float,
) -> tuple[int, float]:
    """Validate response arrays and return the peak index and threshold."""
    if len(frequency_hz) != len(gain_db):
        raise AnalysisError("frequency and gain arrays must have equal lengths")
    if len(frequency_hz) < 2:
        raise AnalysisError("at least two AC samples are required")
    if not isfinite(drop_db) or drop_db <= 0:
        raise AnalysisError("drop_db must be a finite positive number")

    previous_frequency = 0.0
    for index, frequency in enumerate(frequency_hz):
        if not isfinite(frequency) or frequency <= previous_frequency:
            raise AnalysisError("frequencies must be finite, positive, and increasing")
        if not isfinite(gain_db[index]):
            raise AnalysisError("gain values must be finite")
        previous_frequency = frequency

    peak_index = max(range(len(gain_db)), key=gain_db.__getitem__)
    return peak_index, gain_db[peak_index] - drop_db


def _interpolate_log_frequency(
    lower_frequency_hz: float,
    upper_frequency_hz: float,
    lower_gain_db: float,
    upper_gain_db: float,
    threshold_db: float,
) -> float:
    """Interpolate a gain crossing on a logarithmic frequency axis."""
    if upper_gain_db == lower_gain_db:
        return float(upper_frequency_hz)
    fraction = (threshold_db - lower_gain_db) / (upper_gain_db - lower_gain_db)
    lower_log_frequency = log10(lower_frequency_hz)
    upper_log_frequency = log10(upper_frequency_hz)
    return 10 ** (
        lower_log_frequency + fraction * (upper_log_frequency - lower_log_frequency)
    )


def find_cutoff_frequency(
    frequency_hz: Sequence[float],
    gain_db: Sequence[float],
    *,
    drop_db: float = 3.0,
) -> float:
    """Find the first post-peak frequency where gain falls by ``drop_db``.

    The crossing is interpolated in logarithmic frequency, matching the x-axis
    of a Bode plot. The passband reference is the maximum sampled gain.

    Args:
        frequency_hz: Strictly increasing positive sample frequencies.
        gain_db: Gain samples in decibels, one per frequency.
        drop_db: Positive gain decrease that defines the cutoff.

    Returns:
        Interpolated cutoff frequency in hertz.

    Raises:
        AnalysisError: If inputs are invalid or no falling crossing exists.
    """
    peak_index, threshold_db = _validate_response(frequency_hz, gain_db, drop_db)

    for index in range(peak_index + 1, len(gain_db)):
        upper_gain = gain_db[index - 1]
        lower_gain = gain_db[index]
        if upper_gain >= threshold_db >= lower_gain:
            return _interpolate_log_frequency(
                frequency_hz[index - 1],
                frequency_hz[index],
                upper_gain,
                lower_gain,
                threshold_db,
            )

    raise AnalysisError(
        f"no -{drop_db:g} dB crossing found after the passband peak; "
        "increase the AC stop frequency"
    )


def find_highpass_cutoff_frequency(
    frequency_hz: Sequence[float],
    gain_db: Sequence[float],
    *,
    drop_db: float = 3.0,
) -> float:
    """Find the first rising crossing ``drop_db`` below high-pass peak gain.

    Args:
        frequency_hz: Strictly increasing positive sample frequencies.
        gain_db: Gain samples in decibels, one per frequency.
        drop_db: Positive gain decrease that defines the cutoff.

    Returns:
        Interpolated cutoff frequency in hertz.

    Raises:
        AnalysisError: If inputs are invalid or no rising crossing exists.
    """
    peak_index, threshold_db = _validate_response(frequency_hz, gain_db, drop_db)
    for index in range(1, peak_index + 1):
        lower_gain = gain_db[index - 1]
        upper_gain = gain_db[index]
        if lower_gain <= threshold_db <= upper_gain:
            return _interpolate_log_frequency(
                frequency_hz[index - 1],
                frequency_hz[index],
                lower_gain,
                upper_gain,
                threshold_db,
            )

    raise AnalysisError(
        f"no -{drop_db:g} dB rising crossing found before the passband peak; "
        "decrease the AC start frequency"
    )
