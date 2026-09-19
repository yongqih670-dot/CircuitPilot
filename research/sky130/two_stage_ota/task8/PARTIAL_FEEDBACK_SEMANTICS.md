# Task 8 Partial Feedback Semantics

Status: pre-registered before replay, implementation, or new simulation.

Version: task8_hierarchical_lexicographic_feedback_v1

## Unknown values

Every candidate record contains the canonical Task 7 metric names. A physical
metric from an unexecuted analysis is null. Null is never replaced by zero, a
threshold, a penalty metric, a prediction, or a parameter-derived estimate.
The optimizer receives only finite physical values that were actually
measured, plus the scalar objective.

## Normalized measured violation

For a lower-bound constraint, measured violation is
max(0, threshold - value) / max(abs(threshold), 1e-30).

For an upper-bound constraint, measured violation is
max(0, value - threshold) / max(abs(threshold), 1e-30).

Output range contributes its lower and upper components. Operating-region
violation is 1 when invalid and 0 when valid. A required measurement status
that cannot establish the constraint contributes 1. Only constraints
measured at the current stage enter that stage's violation sum.

## Hierarchical scalar

Let b(v) = v / (1 + v), which maps any nonnegative finite violation into
[0, 1). The frozen scalar is:

| Outcome | Objective interval | Formula |
|---|---:|---|
| fully feasible | [0, 0.5] | unchanged Task 7 feasible power secondary |
| transient_rejected | [1, 2) | 1 + b(transient violation sum) |
| ac_rejected | [2, 3) | 2 + b(AC-stage violation sum) |
| op_rejected | [3, 4) | 3 + b(OP-stage violation sum) |

Therefore every later successfully passed stage ranks ahead of every earlier
rejection, and every feasible point ranks ahead of every rejection. Within a
stage, lower real normalized violation ranks first. Ties remain ties; no
unmeasured property breaks them.

Full policy retains the exact Task 7 scalar rather than this partial scalar.
This is part of the explicitly different evaluation policy, while the
feasibility definition is identical.

## Failures

A process, parse, or post-processing failure has null objective and failed
optimizer status, exactly as the common optimizer contract requires. A safe
measured rejection has simulation_status success and a finite tiered
objective. Feedback is deterministic from stored measurements and stage
statuses and must reproduce exactly during checkpoint replay.
