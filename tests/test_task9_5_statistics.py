"""Regression cases for unsupported survival-tail integration."""

import pytest

from circuitpilot.experiments.task9_5_statistics import (
    common_supported_horizon,
    supported_km,
)


def test_common_horizon_uses_both_observed_groups() -> None:
    groups = {
        "full": [(100.0, False), (70.0, True)],
        "hierarchical": [(300.0, False), (200.0, True)],
    }
    horizon = common_supported_horizon(groups)
    assert horizon == 100.0
    assert supported_km(groups["full"], horizon=horizon).rmst == 85.0
    assert supported_km(groups["hierarchical"], horizon=horizon).rmst == 100.0


def test_reject_unsupported_tail_even_for_single_group() -> None:
    with pytest.raises(ValueError, match="exceeds observed support"):
        supported_km([(40.0, True), (60.0, False)], horizon=100.0)


def test_zero_cost_censoring_and_administrative_truncation() -> None:
    estimate = supported_km([(0.0, False), (4.0, True), (10.0, False)], horizon=5.0)
    assert estimate.rmst == 4.5
    assert estimate.points[-1] == (5.0, 0.5, 1, 0, 1)
