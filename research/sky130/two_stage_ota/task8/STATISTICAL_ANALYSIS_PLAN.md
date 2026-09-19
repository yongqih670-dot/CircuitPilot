# Task 8 Statistical Analysis Plan

Status: pre-registered before replay, implementation, or new simulation.

Version: task8_paired_multiaxis_survival_v1

## Units and pairing

The run is the inferential unit. Full and Hierarchical cells are paired by
experiment design, optimizer method, and seed. Calibration, replay, cost
profile, smoke, and shadow calls never enter formal estimates.

## Primary endpoints

Equal-candidate primary endpoints are paired AC calls saved, transient calls
saved, and accumulated ngspice seconds saved. Equal-simulation-time primary
endpoints are run success and accumulated-ngspice-time RMST to first feasible.
Candidate throughput, process calls, outer wall time, and orchestration time
are secondary.

For each endpoint report per method and pooled:

- every paired difference;
- paired mean and median difference;
- deterministic percentile bootstrap 95% confidence interval for the paired
  mean using 10,000 resamples and RNG seed 82008; and
- the direction in which a positive or negative value favors Hierarchical.

No unpaired test substitutes for the paired analysis.

## Survival axes

The event is the first candidate satisfying the unchanged Task 7 feasibility
definition. Each run records event cost and terminal censor cost on:

1. candidate count;
2. AC-analysis count;
3. transient-analysis count; and
4. accumulated ngspice subprocess seconds.

Kaplan–Meier curves and RMST are reported for every design/method/policy/axis.
For a design and axis, the common RMST restriction is the smaller of the
largest observed follow-up values for Full and Hierarchical. This deterministic
shared-support rule prevents extrapolating one policy beyond observed
follow-up. The selected horizon is published with every estimate. A KM median
is null when survival never reaches 0.5.

## Stage and bottleneck summaries

stage_distribution.csv reports op_rejected, ac_rejected,
transient_executed, transient_rejected, fully_feasible, and full_infeasible
counts for each design/method/policy/seed.

first_blocking_constraint.csv reports the first deterministic blocker among
operating_region, power, output_bias, gain, ugf, phase_margin,
positive_slew, and negative_slew. These are descriptive only and cannot
reorder Task 8 stages.

## Integrity gates

Fairness validation permits only evaluation-policy hash differences. It
requires identical Task 7 benchmark/component hashes, search space, PDK,
constraints, measurements, method/seed set, optimizer configuration, and
feasibility definition. It also requires the frozen evaluation-stage,
partial-feedback, simulation-time-budget, and cost-accounting family hashes.

Formal statistics are generated only after offline replay and smoke shadow
audit both report zero false rejection. H1–H4 are decided only by
RESEARCH_HYPOTHESES.md.
