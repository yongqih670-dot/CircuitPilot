# Task 9 Statistical Analysis Plan

Status: pre-registered before nominal-gap evaluation, calibration, replay,
implementation, smoke, or optimizer experiments.

Version: `task9_paired_pvt_multiaxis_survival_v1`

## Units, pairing, and exclusions

The formal run is the inferential unit.  Policies are paired by design
(equal-candidate or equal-time), optimizer (`random`, `de`, `tpe`, `bo`), and
seed (0--9).  Capability probes, nominal-gap designs, Sobol calibration,
offline replay, smoke, and shadow-Full calls never enter formal effect
estimates.

## Primary endpoint

The primary endpoint is accumulated-ngspice-time RMST to the first
PVT-feasible candidate in the equal-simulator-time experiment.  The event is
the first candidate satisfying every hard constraint at every frozen corner.
The Full-versus-Hierarchical contrast is Full RMST minus Hierarchical RMST, so a
positive value favors Hierarchical.

For each method and pooled across the 40 pairs, report every paired difference,
paired mean, paired median, and deterministic 10,000-resample percentile
bootstrap 95% confidence interval for the paired mean (RNG seed `92009`).

## Secondary endpoints

- equal-time run success rate and paired success discordance;
- equal-candidate corners, OP, AC, transient, and process calls saved;
- equal-candidate accumulated ngspice seconds and percentage saved;
- equal-time robust-feasible candidate throughput and budget overshoot;
- outer wall time as orchestration context, not the primary cost measure.

For cost endpoints, savings are Full minus Hierarchical; positive favors the
hierarchy.  Percentage savings use paired Full as denominator.  Report paired
means, medians, all cell differences, and 10,000-resample paired-mean 95% CIs.

## Survival axes

For every design/method/policy report Kaplan--Meier curves, event count,
censoring count, median time when estimable, and RMST on:

1. candidate count;
2. corner evaluations started;
3. OP calls;
4. AC calls;
5. transient calls; and
6. accumulated ngspice subprocess seconds.

For each design/method/axis, the RMST restriction is the smaller of the largest
observed Full and Hierarchical follow-up values.  This deterministic
shared-support rule forbids extrapolation.  A KM median is null if survival
does not reach 0.5.

## Descriptive PVT analyses

From complete Full-PVT matrices report the independent worst-corner frequency
for gain, UGF, phase margin, power, positive slew, negative slew, and output
margin.  Report first failing corner under each frozen order separately.

Failure taxonomy is multilabel and includes process-corner, low-voltage,
high-temperature, operating-region, gain, UGF, phase-margin, power, positive or
negative slew, output-bias, and multiple-constraint failures.  These summaries
cannot alter corner membership or ordering.

## Integrity gates

Formal analysis requires matching Task 7/8 frozen identities, PDK/model hash,
search space, selected specification row, corner-suite hash, corner-order hash,
measurement semantics, objective, cost model, optimizer configuration, paired
method/seed set, and time-budget rule.  Policy identity may differ only in the
pre-frozen Full versus Hierarchical execution behavior and feedback semantics.

Formal execution starts only after calibration replay demonstrates 100%
feasibility identity and zero false acceptance/rejection.  Hypothesis decisions
are made only with `RESEARCH_HYPOTHESES.md`.
