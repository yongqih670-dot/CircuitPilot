# Task 6 Statistical Analysis Plan

Status: pre-registered before implementation, pilot, smoke, and formal data.

Version: task6_paired_survival_effects_v1

Full and Screened are paired by optimizer and seed. Smoke data and cost-profile
pilot data are excluded from research-effect estimates.

For each method and formal experiment, report run success rate, candidate and
expensive-AC time to first feasible, wall time to first feasible, event and
censoring counts, Kaplan-Meier coordinates, RMST by candidate count and
expensive-AC count, total candidates, OP rejected/valid counts, full-AC
candidates, AC analyses avoided, percentage AC saved, process calls, runtime,
and feasible candidate count.

Paired effect estimates use Screened minus Full for time/runtime outcomes and
Full minus Screened for AC analyses saved, so positive AC savings and negative
time differences favor Screened. Censored candidate time is restricted at the
comparison's candidate cap. Censored expensive-AC time is restricted at 200.
Censored wall time is restricted at that run's observed terminal wall time.

For AC analyses saved, restricted time-to-feasible, and wall runtime, report
all ten paired differences, their mean, median, and a two-sided percentile 95%
confidence interval from 10,000 paired-seed bootstrap resamples using NumPy
default_rng seed 62006. Resampling is within method; a pooled descriptive
analysis resamples the 40 method-seed pairs. No null-hypothesis significance
test or post-hoc metric selection is performed.

Kaplan-Meier candidate curves use candidate index. Expensive-AC curves use the
cumulative logical differential plus common-mode AC count at first feasible;
censored runs retain their actual terminal expensive-AC count for descriptive
curves and use the common 200 horizon for RMST comparison. Wall-time survival
is reported only if timestamps are monotonic and finite in every accepted run.

H1-H3 are evaluated only by the decision rules in RESEARCH_HYPOTHESES.md.
Method comparisons are descriptive with ten seeds and must not be presented as
broad generalization.

