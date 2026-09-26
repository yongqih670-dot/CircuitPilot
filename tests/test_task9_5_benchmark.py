"""Corrected benchmark identity must remain distinct and sensitive."""

from circuitpilot.task9_protocol import PVT_BENCHMARK_HASH
from circuitpilot.task9_5_benchmark import benchmark_v2_hash
from circuitpilot.task9_5_region import V1_SEMANTICS


def test_v2_hash_differs_and_tracks_semantics() -> None:
    assert benchmark_v2_hash() != PVT_BENCHMARK_HASH
    assert benchmark_v2_hash(region_version=V1_SEMANTICS) != benchmark_v2_hash()
    assert benchmark_v2_hash(phase_margin_version="critical_pm_v2") != benchmark_v2_hash()
