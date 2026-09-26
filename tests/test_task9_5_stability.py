"""Multiple gain-crossing and critical phase-margin tests."""

from circuitpilot.parser import ACAnalysisResult
from circuitpilot.task9_5_stability import all_unity_crossings, first_and_critical_pm


def test_detects_up_and_down_crossings_and_critical_margin() -> None:
    response = ACAnalysisResult(
        (10.0, 100.0, 1000.0, 10000.0),
        (10.0, -10.0, 10.0, -10.0),
        (-100.0, -120.0, -130.0, -170.0),
    )
    crossings = all_unity_crossings(response)
    assert [item.direction for item in crossings] == [
        "descending", "ascending", "descending"]
    assert [round(item.frequency_hz, 3) for item in crossings] == [
        31.623, 316.228, 3162.278]
    assert first_and_critical_pm(crossings) == (70.0, 30.0)


def test_no_descending_crossing_has_no_phase_margin() -> None:
    response = ACAnalysisResult((10.0, 100.0), (-10.0, 10.0), (-20.0, -40.0))
    assert first_and_critical_pm(all_unity_crossings(response)) == (None, None)
