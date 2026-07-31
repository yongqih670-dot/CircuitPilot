"""Bode plot generation for AC analysis results."""

from __future__ import annotations

from math import isfinite
from pathlib import Path

from circuitpilot.exceptions import PlotError
from circuitpilot.parser import ACAnalysisResult


def plot_bode(
    result: ACAnalysisResult,
    output_path: str | Path,
    *,
    cutoff_frequency_hz: float | None = None,
    title: str = "Circuit Frequency Response",
    show: bool = False,
) -> Path:
    """Create a two-panel magnitude and phase Bode plot.

    Args:
        result: Parsed AC response samples.
        output_path: Image destination; its format follows the file suffix.
        cutoff_frequency_hz: Optional cutoff marker drawn on both panels.
        title: Plot title describing the configured circuit.
        show: Display an interactive window after saving the image.

    Returns:
        Absolute path of the saved plot.

    Raises:
        PlotError: If data is empty, the marker is invalid, or saving fails.
    """
    if len(result) == 0:
        raise PlotError("cannot plot an empty AC analysis result")
    if not (
        len(result.frequency_hz) == len(result.gain_db) == len(result.phase_deg)
    ):
        raise PlotError("frequency, gain, and phase arrays must have equal lengths")
    if cutoff_frequency_hz is not None and (
        not isfinite(cutoff_frequency_hz) or cutoff_frequency_hz <= 0
    ):
        raise PlotError("cutoff_frequency_hz must be finite and positive")

    # Import lazily so parsing and analysis remain usable in minimal contexts.
    import matplotlib.pyplot as plt

    destination = Path(output_path).resolve()
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PlotError(
            f"failed to create plot directory '{destination.parent}': {exc}"
        ) from exc

    figure, (gain_axis, phase_axis) = plt.subplots(
        2, 1, figsize=(9, 7), sharex=True, constrained_layout=True
    )
    try:
        gain_axis.semilogx(result.frequency_hz, result.gain_db, color="#1769aa")
        gain_axis.set_ylabel("Gain (dB)")
        gain_axis.set_title(title)
        gain_axis.grid(True, which="both", linestyle=":", alpha=0.6)

        phase_axis.semilogx(result.frequency_hz, result.phase_deg, color="#c44e52")
        phase_axis.set_xlabel("Frequency (Hz)")
        phase_axis.set_ylabel("Phase (degrees)")
        phase_axis.grid(True, which="both", linestyle=":", alpha=0.6)

        if cutoff_frequency_hz is not None:
            label = f"Cutoff: {cutoff_frequency_hz:.4g} Hz"
            for axis in (gain_axis, phase_axis):
                axis.axvline(
                    cutoff_frequency_hz,
                    color="#2e7d32",
                    linestyle="--",
                    linewidth=1.2,
                    label=label,
                )
                axis.legend(loc="best")

        try:
            figure.savefig(destination, dpi=150)
        except (OSError, ValueError) as exc:
            raise PlotError(f"failed to save Bode plot '{destination}': {exc}") from exc
        if show:
            plt.show()
    finally:
        plt.close(figure)

    return destination
