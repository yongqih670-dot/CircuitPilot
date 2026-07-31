from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from circuitpilot.parser import ACAnalysisResult
from circuitpilot.plotting import plot_bode


def test_plot_bode_writes_nonempty_image(tmp_path: Path) -> None:
    response = ACAnalysisResult(
        frequency_hz=(10.0, 100.0, 1_000.0, 10_000.0),
        gain_db=(-0.001, -0.04, -3.01, -20.04),
        phase_deg=(-0.6, -5.7, -45.0, -84.3),
    )

    destination = plot_bode(
        response,
        tmp_path / "plots" / "bode.png",
        cutoff_frequency_hz=1_000.0,
    )

    assert destination.is_file()
    assert destination.stat().st_size > 1_000

