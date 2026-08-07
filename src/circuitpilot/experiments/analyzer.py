"""Physical metric extraction from parsed simulator evidence only."""

from __future__ import annotations

from math import log10
from typing import Mapping, Protocol

from circuitpilot.analysis import find_cutoff_frequency
from circuitpilot.circuit_config import CircuitType
from circuitpilot.exceptions import AnalysisError
from circuitpilot.experiments.config import ExperimentConfig
from circuitpilot.experiments.simulation import CandidateSimulation
from circuitpilot.power_metrics import derived_rc_power


class CandidateAnalyzer(Protocol):
    """Analyzer dependency used by the single common experiment runner."""

    def extract(
        self,
        simulation: CandidateSimulation,
        parameters: Mapping[str, float | int],
    ) -> dict[str, float]:
        """Return physical metrics derived only from simulator evidence."""


def _interpolate_log_frequency(
    frequencies: tuple[float, ...],
    values: tuple[float, ...],
    frequency_hz: float,
) -> float:
    """Interpolate one response value on the AC logarithmic frequency axis."""
    if frequency_hz < frequencies[0] or frequency_hz > frequencies[-1]:
        raise AnalysisError(
            f"metric frequency {frequency_hz:g} Hz is outside simulated AC range"
        )
    if frequency_hz == frequencies[0]:
        return values[0]
    for index in range(1, len(frequencies)):
        if frequency_hz <= frequencies[index]:
            lower_frequency = frequencies[index - 1]
            upper_frequency = frequencies[index]
            if frequency_hz == upper_frequency:
                return values[index]
            fraction = (log10(frequency_hz) - log10(lower_frequency)) / (
                log10(upper_frequency) - log10(lower_frequency)
            )
            return values[index - 1] + fraction * (values[index] - values[index - 1])
    return values[-1]


class RCLowPassAnalyzer:
    """Extract requested RC metrics from parsed AC response arrays."""

    _BANDWIDTH_NAMES = {
        "bandwidth",
        "bandwidth_hz",
        "cutoff_frequency",
        "cutoff_frequency_hz",
    }
    _GAIN_NAMES = {"gain", "gain_db"}
    _PHASE_NAMES = {"phase", "phase_deg"}
    _POWER_NAMES = {"power", "derived_rc_power", "derived_rc_power_w"}

    def __init__(self, config: ExperimentConfig) -> None:
        """Collect metric frequencies and reject ambiguous duplicate requests."""
        self._config = config
        frequencies: dict[str, float | None] = {}
        for definition in (*config.objectives, *config.constraints):
            existing = frequencies.get(definition.metric)
            if definition.metric in frequencies and existing != definition.frequency_hz:
                raise ValueError(
                    f"metric '{definition.metric}' uses conflicting frequency_hz values"
                )
            frequencies[definition.metric] = definition.frequency_hz
        self._frequencies = frequencies

    def extract(
        self,
        simulation: CandidateSimulation,
        parameters: Mapping[str, float | int],
    ) -> dict[str, float]:
        """Compute only explicitly requested metrics plus the raw sample count."""
        response = simulation.response
        metrics: dict[str, float] = {"sample_count": float(len(response))}
        cutoff: float | None = None
        for name, frequency_hz in self._frequencies.items():
            if name in self._BANDWIDTH_NAMES:
                if cutoff is None:
                    cutoff = find_cutoff_frequency(
                        response.frequency_hz, response.gain_db
                    )
                metrics[name] = cutoff
                continue
            selected_frequency = frequency_hz or response.frequency_hz[0]
            gain = _interpolate_log_frequency(
                response.frequency_hz, response.gain_db, selected_frequency
            )
            if name in self._GAIN_NAMES:
                metrics[name] = gain
                continue
            phase = _interpolate_log_frequency(
                response.frequency_hz, response.phase_deg, selected_frequency
            )
            if name in self._PHASE_NAMES:
                metrics[name] = phase
                continue
            if name in self._POWER_NAMES:
                metrics[name] = derived_rc_power(
                    gain_db=gain,
                    phase_deg=phase,
                    resistance_ohm=float(parameters["resistance"]),
                    circuit_type=CircuitType.RC_LOWPASS,
                )
                continue
            raise AnalysisError(
                f"metric '{name}' is not available for the rc_lowpass research baseline"
            )
        return metrics
