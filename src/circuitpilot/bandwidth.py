"""Explicit -3 dB bandwidth measurement with right-censoring semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite, log10
from typing import Sequence


BANDWIDTH_SEMANTICS_VERSION = "post_peak_minus_3db_right_censoring_v1"


class BandwidthStatus(str, Enum):
    """Mutually exclusive outcomes of one fixed-window bandwidth measurement."""

    MEASURED = "measured"
    RIGHT_CENSORED = "right_censored"
    INVALID_RESPONSE = "invalid_response"
    ANALYSIS_ERROR = "analysis_error"


@dataclass(frozen=True, slots=True)
class BandwidthMeasurement:
    """A bandwidth value or a truthful bound/status when no exact value exists."""

    bandwidth_status: BandwidthStatus
    bandwidth_hz: float | None
    bandwidth_lower_bound_hz: float | None
    reference_gain_db: float | None
    peak_frequency_hz: float | None
    message: str | None = None

    @property
    def measurement_status(self) -> str:
        """Return the run-level measurement category used by experiment records."""
        if self.bandwidth_status in {
            BandwidthStatus.MEASURED,
            BandwidthStatus.RIGHT_CENSORED,
        }:
            return "complete"
        return self.bandwidth_status.value


def measure_bandwidth(
    frequency_hz: Sequence[float],
    gain_db: Sequence[float],
    *,
    drop_db: float = 3.0,
) -> BandwidthMeasurement:
    """Measure the first post-peak crossing or report fixed-window censoring.

    The exact crossing is interpolated on the logarithmic frequency axis.  A
    valid response that remains above the threshold through the final sample is
    right-censored; the final frequency is recorded only as a lower bound.
    """
    try:
        frequencies = tuple(float(value) for value in frequency_hz)
        gains = tuple(float(value) for value in gain_db)
        if len(frequencies) != len(gains) or len(frequencies) < 2:
            return BandwidthMeasurement(
                BandwidthStatus.INVALID_RESPONSE,
                None,
                None,
                None,
                None,
                "bandwidth measurement requires at least two paired samples",
            )
        if not isfinite(drop_db) or drop_db <= 0:
            return BandwidthMeasurement(
                BandwidthStatus.ANALYSIS_ERROR,
                None,
                None,
                None,
                None,
                "drop_db must be finite and positive",
            )
        if not all(isfinite(value) for value in (*frequencies, *gains)):
            return BandwidthMeasurement(
                BandwidthStatus.INVALID_RESPONSE,
                None,
                None,
                None,
                None,
                "frequency and gain samples must be finite",
            )
        if frequencies[0] <= 0 or any(
            current <= previous
            for previous, current in zip(frequencies, frequencies[1:])
        ):
            return BandwidthMeasurement(
                BandwidthStatus.INVALID_RESPONSE,
                None,
                None,
                None,
                None,
                "frequency samples must be positive and strictly increasing",
            )

        peak_index = max(range(len(gains)), key=gains.__getitem__)
        reference_gain = gains[peak_index]
        threshold = reference_gain - drop_db
        for index in range(peak_index + 1, len(gains)):
            if gains[index] > threshold:
                continue
            lower_gain = gains[index - 1]
            upper_gain = gains[index]
            lower_frequency = frequencies[index - 1]
            upper_frequency = frequencies[index]
            if upper_gain == lower_gain:
                crossing = upper_frequency
            else:
                fraction = (threshold - lower_gain) / (upper_gain - lower_gain)
                crossing = 10 ** (
                    log10(lower_frequency)
                    + fraction * (log10(upper_frequency) - log10(lower_frequency))
                )
            return BandwidthMeasurement(
                BandwidthStatus.MEASURED,
                crossing,
                None,
                reference_gain,
                frequencies[peak_index],
            )

        return BandwidthMeasurement(
            BandwidthStatus.RIGHT_CENSORED,
            None,
            frequencies[-1],
            reference_gain,
            frequencies[peak_index],
            "valid response has no post-peak -3 dB crossing in the fixed window",
        )
    except (ArithmeticError, OverflowError, TypeError, ValueError) as exc:
        return BandwidthMeasurement(
            BandwidthStatus.ANALYSIS_ERROR,
            None,
            None,
            None,
            None,
            str(exc),
        )
