from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from circuitpilot.experiments.task8_statistics import kaplan_meier, paired_effect


ROOT = Path(__file__).resolve().parents[1]
TASK8 = ROOT / "research" / "sky130" / "two_stage_ota" / "task8"


def test_task8_paired_bootstrap_is_deterministic() -> None:
    first = paired_effect([1.0, 2.0, 3.0], resamples=250)
    second = paired_effect([1.0, 2.0, 3.0], resamples=250)
    assert first == second
    assert first["pairs"] == 3
    assert first["mean_difference"] == pytest.approx(2.0)
    assert first["median_difference"] == pytest.approx(2.0)
    assert first["ci95_low"] <= 2.0 <= first["ci95_high"]


def test_task8_kaplan_meier_truncates_at_shared_horizon() -> None:
    estimate = kaplan_meier([(1.0, True), (2.0, False), (4.0, True)], horizon=3.0)
    assert estimate.horizon == 3.0
    assert estimate.rmst == pytest.approx(7.0 / 3.0)
    assert estimate.median_time_to_event is None
    assert [(point.time, point.events, point.censored) for point in estimate.points] == [
        (1.0, 1, 0),
        (2.0, 0, 1),
        (3.0, 0, 1),
    ]


def test_task8_final_statistics_artifacts_are_complete() -> None:
    summary = json.loads(
        (TASK8 / "results" / "task8_summary.json").read_text(encoding="utf-8")
    )
    decisions = json.loads(
        (TASK8 / "results" / "statistics" / "hypothesis_decisions.json").read_text(
            encoding="utf-8"
        )
    )
    effects = json.loads(
        (TASK8 / "results" / "statistics" / "paired_effects.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["status"] == "complete"
    assert summary["simulation_failure_count"] == 0
    assert all(summary["hypothesis_decisions"].values())
    assert all(decisions[name]["supported"] for name in ("H1", "H2", "H3", "H4"))
    assert decisions["H4"]["replay_candidates"] == 2000
    assert decisions["H4"]["replay_false_rejections"] == 0
    assert decisions["H4"]["shadow_false_rejections"] == 0
    pooled = {
        row["outcome"]: row
        for row in effects
        if row["experiment_design"] == "equal_candidate"
        and row["method"] == "pooled_descriptive"
    }
    assert pooled["total_analyses_saved"]["paired_differences"] == pooled[
        "process_calls_saved"
    ]["paired_differences"]

    statistics = TASK8 / "results" / "statistics"
    with (statistics / "stage_distribution.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        assert len(list(csv.DictReader(handle))) == 184
    with (statistics / "first_blocking_constraint.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        assert len(list(csv.DictReader(handle))) == 184 * 8
    with (statistics / "rmst_summary.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        assert len(list(csv.DictReader(handle))) == 120

    evidence = json.loads(
        (TASK8 / "results" / "best_raw_evidence" / "index.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(evidence) == summary["best_raw_evidence_count"] == 10
    assert all((ROOT / item["destination"]).is_dir() for item in evidence)

    report = (TASK8 / "TASK8_HIERARCHICAL_EVALUATION_REPORT.md").read_text(
        encoding="utf-8"
    )
    assert all(f"## {section}." in report for section in range(1, 26))
