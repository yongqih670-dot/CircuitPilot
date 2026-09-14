from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from circuitpilot.experiments.optimizers.base import Optimizer
from circuitpilot.experiments.task6_policy import (
    CandidateCostTracker,
    FullEvaluationPolicy,
    OperatingPointScreeningPolicy,
    Task6PolicyOutcome,
)
from circuitpilot.experiments.task6_recorder import Task6Recorder
from circuitpilot.experiments.task6_runner import (
    Task6RunDefinition,
    Task6Runner,
)
from circuitpilot.experiments.task6_statistics import validate_task6_fairness
from circuitpilot.experiments.seeding import initialize_seeds
from circuitpilot.run_directory import prepare_research_run_directory
from circuitpilot.sky130_differential_amplifier import (
    DEVICE_ROLES,
    DifferentialOperatingPoint,
)
from circuitpilot.task6_physics import (
    PhysicsAssessment,
    classify_task6_physics,
    generate_task6_ac_only_netlist,
    generate_task6_op_only_netlist,
    rejected_policy_objective,
    task6_operating_point_metrics,
)
from circuitpilot.task6_protocol import (
    FULL_POLICY,
    SCREENED_POLICY,
    TASK5_BENCHMARK_HASH,
    evaluation_policy_family_hash,
    evaluation_policy_hash,
)


FROZEN = Path(
    "research/sky130/differential_amplifier/"
    "differential_amplifier_frozen.yaml"
)
PARAMETERS = {
    "input_pair_width_m": 3e-6,
    "input_pair_length_m": 0.3e-6,
    "active_load_width_m": 6e-6,
    "active_load_length_m": 0.5e-6,
    "tail_width_m": 4e-6,
    "tail_length_m": 0.5e-6,
    "tail_bias_v": 0.75,
}


def _op(
    *,
    output: float = 0.9,
    overrides: dict[str, dict[str, float]] | None = None,
) -> DifferentialOperatingPoint:
    devices = {
        "input_m1": {"vgs": 0.8, "vds": 0.6, "vth": 0.5},
        "input_m2": {"vgs": 0.8, "vds": 0.6, "vth": 0.5},
        "load_mirror": {"vgs": -0.8, "vds": -0.6, "vth": -0.5},
        "load_output": {"vgs": -0.8, "vds": -0.6, "vth": -0.5},
        "tail": {"vgs": 0.8, "vds": 0.6, "vth": 0.5},
    }
    for role, values in (overrides or {}).items():
        devices[role].update(values)
    return DifferentialOperatingPoint(
        supply_voltage_v=1.8,
        input_positive_voltage_v=0.9,
        input_negative_voltage_v=0.9,
        output_voltage_v=output,
        tail_node_voltage_v=0.4,
        supply_current_a=-0.0001,
        tail_current_a=0.0001,
        device_quantities=devices,
    )


@pytest.mark.parametrize(
    ("overrides", "output", "expected"),
    [
        ({"input_m1": {"vgs": 0.4}}, 0.9, "input_pair_off"),
        ({"input_m1": {"vds": 0.1}}, 0.9, "input_pair_not_saturated"),
        ({"load_mirror": {"vgs": -0.4}}, 0.9, "active_load_off"),
        ({"load_output": {"vds": -0.1}}, 0.9, "active_load_not_saturated"),
        ({"tail": {"vgs": 0.4}}, 0.9, "tail_off"),
        ({"tail": {"vds": 0.1}}, 0.9, "tail_not_saturated"),
        ({}, 0.1, "output_headroom_invalid"),
    ],
)
def test_transparent_physics_taxonomy(overrides, output, expected) -> None:
    result = classify_task6_physics(_op(output=output, overrides=overrides))
    assert result.physics_status == "invalid"
    assert result.violation_count == 1
    assert result.violation_types == (expected,)
    assert result.op_constraint_violation > 0


def test_multiple_physics_violations_preserve_primary_bits() -> None:
    result = classify_task6_physics(
        _op(
            output=1.7,
            overrides={
                "input_m1": {"vgs": 0.4},
                "tail": {"vds": 0.1},
            },
        )
    )
    assert result.violation_count == 3
    assert result.violation_mask == 1 | 32 | 64
    assert result.violation_types[-1] == "multiple_physics_violations"


def test_valid_physics_has_zero_mask_and_violation() -> None:
    result = classify_task6_physics(_op())
    assert result.physics_status == "valid"
    assert result.violation_mask == result.violation_count == 0
    assert result.violation_types == ()
    assert result.op_constraint_violation == 0


def test_op_only_metrics_never_synthesize_ac_values() -> None:
    metrics = task6_operating_point_metrics(
        _op(overrides={"tail": {"vds": 0.1}})
    )
    assert metrics["dc_power_w"] == pytest.approx(0.00018)
    for name in (
        "differential_gain_db", "common_mode_gain_db", "cmrr_db",
        "cmrr_lower_bound_db", "bandwidth_hz", "bandwidth_lower_bound_hz",
    ):
        assert metrics[name] is None


def test_rejected_feedback_is_finite_ordered_and_above_full_hierarchy() -> None:
    first = rejected_policy_objective(0.1)
    second = rejected_policy_objective(1.0)
    assert 1000.0 < first < second < 1001.0


def test_task6_netlists_keep_frozen_topology_and_separate_stages() -> None:
    config = Task6RunDefinition(
        FROZEN, "random", SCREENED_POLICY, 0, 2, None, "smoke", Path("unused")
    ).resolved_config().circuit_config
    op_text = generate_task6_op_only_netlist(
        config, PARAMETERS, invariant_path="I", nfet_corner_path="N",
        pfet_corner_path="P", op_output_path="O", device_op_output_path="D",
    )
    ac_text = generate_task6_ac_only_netlist(
        config, PARAMETERS, invariant_path="I", nfet_corner_path="N",
        pfet_corner_path="P", differential_ac_output_path="A",
        common_mode_ac_output_path="C", start_frequency_hz=10,
        stop_frequency_hz=1e10, points_per_decade=30,
    )
    assert op_text.count("\nop\n") == 1 and "\nac dec " not in op_text
    assert "\nop\n" not in ac_text and ac_text.count("\nac dec ") == 1
    for text in (op_text, ac_text):
        assert "sky130_fd_pr__nfet_01v8 W=3 L=0.3" in text
        assert "sky130_fd_pr__pfet_01v8 W=6 L=0.5" in text


def test_screened_reject_does_not_launch_ac(monkeypatch, tmp_path: Path) -> None:
    definition = Task6RunDefinition(
        FROZEN, "random", SCREENED_POLICY, 0, 2, None, "smoke", tmp_path
    )
    policy = OperatingPointScreeningPolicy(definition.resolved_config())
    launches = []
    monkeypatch.setattr(
        "circuitpilot.experiments.task6_policy.run_task6_op_only",
        lambda *args, on_ngspice_launch, **kwargs: (
            on_ngspice_launch(),
            SimpleNamespace(operating_point=_op(overrides={"tail": {"vds": 0.1}})),
        )[1],
    )
    monkeypatch.setattr(
        "circuitpilot.experiments.task6_policy.run_task6_ac_only",
        lambda *args, **kwargs: launches.append("ac"),
    )
    cost = CandidateCostTracker()
    outcome = policy.evaluate(PARAMETERS, tmp_path, cost)
    assert outcome.evaluation_stage == "op_rejected"
    assert outcome.objective_value > 1000
    assert launches == []
    assert cost.ngspice_process_calls == cost.dc_op_calls == 1
    assert cost.expensive_ac_analysis_count == 0


class SequenceOptimizer(Optimizer):
    def __init__(self, candidates):
        self.candidates = list(candidates)
        self.index = 0
        self.feedback = []

    def ask(self):
        value = dict(self.candidates[self.index])
        self.index += 1
        return value

    def tell(self, parameters, metrics, objective, simulation_status):
        self.feedback.append((dict(parameters), dict(metrics), objective, simulation_status))

    def save_state(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(self.index), encoding="utf-8")
        return path

    def load_state(self, path):
        self.index = int(Path(path).read_text(encoding="utf-8"))


class FakePolicy:
    def __init__(self, name: str):
        self.policy_name = name
        self.policy_hash = evaluation_policy_hash(name)

    def evaluate(self, parameters, evaluation_directory, cost):
        invalid = float(parameters["tail_bias_v"]) < 0.7
        if self.policy_name == FULL_POLICY:
            cost.mark_full_process()
        else:
            cost.mark_op_process()
            if not invalid:
                cost.mark_ac_process()
        physics = (
            PhysicsAssessment("invalid", 32, 1, ("tail_not_saturated",), 0.2, {})
            if invalid else PhysicsAssessment("valid", 0, 0, (), 0.0, {})
        )
        if self.policy_name == SCREENED_POLICY and invalid:
            return Task6PolicyOutcome(
                metrics=task6_operating_point_metrics(
                    _op(overrides={"tail": {"vds": 0.1}})
                ),
                objective_value=rejected_policy_objective(0.2),
                constraint_violation=0.2, is_feasible=False,
                measurement_status="op_only_complete", bandwidth_status=None,
                bandwidth_lower_bound_hz=None, cmrr_status=None,
                cmrr_lower_bound_db=None, evaluation_stage="op_rejected",
                physics=physics,
            )
        return Task6PolicyOutcome(
            metrics={"dc_power_w": 0.0002, "differential_gain_db": 20.0},
            objective_value=0.0002, constraint_violation=0.0,
            is_feasible=not invalid, measurement_status="complete",
            bandwidth_status="measured", bandwidth_lower_bound_hz=None,
            cmrr_status="measured", cmrr_lower_bound_db=None,
            evaluation_stage="full_evaluated", physics=physics,
        )


def _candidates():
    return [
        {**PARAMETERS, "tail_bias_v": 0.6},
        {**PARAMETERS, "tail_bias_v": 0.75},
        {**PARAMETERS, "tail_bias_v": 0.8},
        {**PARAMETERS, "tail_bias_v": 0.9},
    ]


def _runner(tmp_path, definition, optimizer, policy, resume=False):
    run = prepare_research_run_directory(
        tmp_path / "run", resume=resume,
        configuration_sha256=definition.identity_sha256(),
    )
    recorder = Task6Recorder(run.path)
    return Task6Runner(
        definition=definition, config=definition.resolved_config(), run=run,
        optimizer=optimizer, policy=policy, recorder=recorder,
        seed_registry=initialize_seeds(definition.seed).registry,
        optimizer_state_path=run.path / "summary" / "optimizer_state.json",
    )


def test_equal_cost_budget_uses_logical_ac_calls(tmp_path: Path) -> None:
    definition = Task6RunDefinition(
        FROZEN, "random", FULL_POLICY, 0, 300, 4,
        "formal_equal_cost", tmp_path,
    )
    result = _runner(
        tmp_path, definition, SequenceOptimizer(_candidates()),
        FakePolicy(FULL_POLICY),
    ).run_to_budget()
    assert len(result.records) == 2
    assert result.cost_totals["expensive_ac_analysis_count"] == 4


def test_screened_costs_and_event_axes_are_recorded(tmp_path: Path) -> None:
    definition = Task6RunDefinition(
        FROZEN, "random", SCREENED_POLICY, 0, 2, None, "smoke", tmp_path
    )
    result = _runner(
        tmp_path, definition, SequenceOptimizer(_candidates()),
        FakePolicy(SCREENED_POLICY),
    ).run_to_budget()
    rejected, feasible = result.records
    assert rejected.evaluation_stage == "op_rejected"
    assert rejected.simulation_status == "success"
    assert rejected.expensive_ac_analysis_count == 0
    assert not rejected.event_observed
    assert feasible.event_observed
    assert feasible.expensive_ac_calls_cumulative == 2
    assert result.cost_totals == {
        "candidate_evaluations": 2, "ngspice_process_calls": 3,
        "dc_op_calls": 2, "differential_ac_calls": 1,
        "common_mode_ac_calls": 1, "full_ac_candidate_count": 1,
        "expensive_ac_analysis_count": 2, "physical_analysis_calls": 3,
    }


def test_task6_resume_continues_exact_candidate_sequence(tmp_path: Path) -> None:
    definition = Task6RunDefinition(
        FROZEN, "random", SCREENED_POLICY, 0, 4, None, "smoke", tmp_path
    )
    first_optimizer = SequenceOptimizer(_candidates())
    partial = _runner(
        tmp_path, definition, first_optimizer, FakePolicy(SCREENED_POLICY)
    ).run_to_budget(max_new_candidates=2)
    assert not partial.completed
    resumed_optimizer = SequenceOptimizer(_candidates())
    resumed_optimizer.load_state(
        tmp_path / "run" / "summary" / "optimizer_state.json"
    )
    complete = _runner(
        tmp_path, definition, resumed_optimizer,
        FakePolicy(SCREENED_POLICY), resume=True,
    ).run_to_budget()
    assert complete.completed
    assert [row.iteration for row in complete.records] == [1, 2, 3, 4]
    assert [row.parameters for row in complete.records] == _candidates()
    assert sum(row.event_observed for row in complete.records) == 1


def test_recorder_rejects_ac_metrics_on_op_rejection(tmp_path: Path) -> None:
    definition = Task6RunDefinition(
        FROZEN, "random", SCREENED_POLICY, 0, 1, None, "smoke", tmp_path
    )
    result = _runner(
        tmp_path, definition, SequenceOptimizer(_candidates()),
        FakePolicy(SCREENED_POLICY),
    ).run_to_budget()
    with pytest.raises(ValueError, match="AC metrics"):
        replace(
            result.records[0],
            raw_metrics={
                **result.records[0].raw_metrics,
                "differential_gain_db": 10.0,
            },
        )


def test_policy_hashes_bind_same_frozen_task5_benchmark() -> None:
    definition = Task6RunDefinition(
        FROZEN, "de", SCREENED_POLICY, 7, 300, 200,
        "formal_equal_cost", Path("unused"),
    )
    assert definition.resolved_config().computed_benchmark_hash() == TASK5_BENCHMARK_HASH
    assert evaluation_policy_hash(FULL_POLICY) != evaluation_policy_hash(SCREENED_POLICY)
    assert len(evaluation_policy_family_hash()) == 64


def test_fairness_validator_rejects_cost_drift() -> None:
    base = {
        "_completed": True, "experiment_design": "smoke",
        "candidate_cap": 1, "expensive_ac_budget": None,
        "_task5_benchmark_hash": TASK5_BENCHMARK_HASH,
        "_task6_policy_family_hash": evaluation_policy_family_hash(),
        "method": "random", "seed": 0, "candidate_evaluations": 1,
        "expensive_ac_analysis_count": 2, "ngspice_process_calls": 1,
        "dc_op_calls": 1, "differential_ac_calls": 1,
        "common_mode_ac_calls": 1, "full_ac_candidate_count": 1,
        "physical_analysis_calls": 2,
    }
    rows = [
        {
            **base, "evaluation_policy": FULL_POLICY,
            "_evaluation_policy_hash": evaluation_policy_hash(FULL_POLICY),
        },
        {
            **base, "evaluation_policy": SCREENED_POLICY,
            "_evaluation_policy_hash": evaluation_policy_hash(SCREENED_POLICY),
            "ngspice_process_calls": 99,
        },
    ]
    with pytest.raises(Exception, match="Screened policy cost"):
        validate_task6_fairness(
            rows, expected_methods=("random",),
            expected_policies=(FULL_POLICY, SCREENED_POLICY),
            expected_seeds=(0,), candidate_cap=1, expensive_ac_budget=None,
            experiment_design="smoke",
        )


@pytest.mark.integration
def test_real_invalid_op_is_rejected_without_ac(tmp_path: Path) -> None:
    definition = Task6RunDefinition(
        FROZEN, "random", SCREENED_POLICY, 0, 1, None, "smoke", tmp_path
    )
    candidates = json.loads(
        Path(
            "research/sky130/differential_amplifier/task6/"
            "pilot_candidates.json"
        ).read_text(encoding="utf-8")
    )["candidates"]
    cost = CandidateCostTracker()
    outcome = OperatingPointScreeningPolicy(
        definition.resolved_config()
    ).evaluate(candidates[0], tmp_path / "invalid", cost)
    assert outcome.evaluation_stage == "op_rejected"
    assert outcome.physics.physics_status == "invalid"
    assert cost.ngspice_process_calls == 1
    assert cost.expensive_ac_analysis_count == 0
    assert not (tmp_path / "invalid" / "ac_stage").exists()
    assert all(
        outcome.metrics[name] is None
        for name in (
            "differential_gain_db", "common_mode_gain_db", "cmrr_db",
            "bandwidth_hz",
        )
    )


@pytest.mark.integration
def test_real_valid_screened_ac_matches_task5_full_path(tmp_path: Path) -> None:
    definition = Task6RunDefinition(
        FROZEN, "random", SCREENED_POLICY, 0, 1, None, "smoke", tmp_path
    )
    config = definition.resolved_config()
    screened_cost, full_cost = CandidateCostTracker(), CandidateCostTracker()
    screened = OperatingPointScreeningPolicy(config).evaluate(
        PARAMETERS, tmp_path / "screened", screened_cost
    )
    full = FullEvaluationPolicy(config).evaluate(
        PARAMETERS, tmp_path / "full", full_cost
    )
    assert screened.evaluation_stage == full.evaluation_stage == "full_evaluated"
    assert screened.physics.physics_status == "valid"
    assert screened_cost.ngspice_process_calls == 2
    assert screened_cost.expensive_ac_analysis_count == 2
    assert full_cost.ngspice_process_calls == 1
    assert full_cost.expensive_ac_analysis_count == 2
    for name in (
        "differential_gain_db", "common_mode_gain_db", "cmrr_db",
        "bandwidth_hz", "dc_power_w", "output_dc_voltage",
    ):
        assert screened.metrics[name] == pytest.approx(
            full.metrics[name], rel=1e-8, abs=1e-12
        )
