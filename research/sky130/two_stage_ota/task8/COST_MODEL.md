# Task 8 Cost Model and Budgets

Status: pre-registered before replay, implementation, or new simulation.

Version: task8_subprocess_time_and_stage_counts_v1

## Per-candidate accounting

Every online candidate stores:

- candidate_count;
- ngspice_process_calls;
- op_calls, ac_calls, and transient_calls;
- logical_high_fidelity_calls, equal to the three analysis-call sum;
- accumulated_ngspice_seconds;
- outer_wall_seconds;
- orchestration_seconds;
- evaluation_stage and first_blocking_constraint;
- cumulative forms of all call counts and accumulated simulator seconds.

accumulated_ngspice_seconds is the sum of SimulationResult.elapsed_seconds
for completed ngspice subprocesses. If an attempted subprocess raises before
returning a SimulationResult, its measured call-boundary elapsed duration is
recorded with an explicit failure-estimate flag. outer_wall_seconds spans the
whole candidate. orchestration_seconds is the nonnegative residual after
subtracting accumulated subprocess time from outer wall time.

Shadow-Full smoke analyses use parallel shadow_* cost fields and never count
toward online candidate, process, analysis, or budget totals.

## Designs

| Design | Policies | Seeds | Candidate rule | Simulation-time rule |
|---|---|---|---|---|
| smoke | Full, Hierarchical | 0–2 | 25 exactly | none |
| formal_equal_candidate | Full, Hierarchical | 0–9 | 50 exactly | descriptive |
| formal_equal_simulation_time | Full, Hierarchical | 0–9 | cap 300 | 90.0 accumulated ngspice seconds |

All designs use Random, DE, TPE, and BO.

The 90.0 s budget is fixed from the Task 7 per-analysis medians:
50 × (0.578 + 0.578 + 0.609) = 88.25 s, rounded upward before Task 8 runs.
The 300-candidate cap prevents unbounded cheap rejection throughput.

## Budget stopping

A new candidate starts only while accumulated simulator time is below 90.0 s
and candidate count is below 300. Once started, the candidate completes every
analysis required by its selected policy. The budget is checked after each
completed analysis for telemetry, but stopping is deferred to the candidate's
terminal stage so no pending optimizer candidate receives incomplete or
synthetic feedback. ngspice is never killed to hit the budget.

The last terminal analysis may cross 90.0 s. The run stores
budget_overshoot_seconds = max(0, accumulated_ngspice_seconds - 90.0).
Both policies use this exact rule.

## Pre-formal cost profile

The fixed profile set is the first 16 candidates by iteration from frozen
Task 7 formal Random seed 0. Without using their outcomes to change policy or
budget, every candidate is re-run in three modes: OP-only, OP+AC, and Full
OP+AC+transient. The profile reports median, mean, Q1, Q3, and IQR for
subprocess and outer time. It is not an optimizer experiment.
