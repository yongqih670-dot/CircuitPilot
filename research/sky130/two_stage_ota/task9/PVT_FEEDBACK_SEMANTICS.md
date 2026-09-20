# Task 9 Partial PVT Feedback Semantics

Status: frozen before evaluator implementation, tests, smoke, or formal runs.

Version: `task9_measured_progress_lexicographic_feedback_v1`

## Principles

Full and Hierarchical share the same PVT feasibility and feasible objective.
Partial feedback uses only measured stages/corners and real constraint/status
violations.  Unrun metrics stay null and contribute no predicted value.  The
feedback cannot change search bounds, corner order, or evaluation policy.

## Progress tier

There are 45 ordered stage opportunities: three stages for each of 15 corners.
`progress_units` counts safely passed stages before the terminal failure:

- OP failure: zero new units at that corner;
- AC failure: one new unit (OP passed);
- transient failure: two new units (OP and AC passed);
- corner pass: three new units.

Thus a candidate that passes more corners/stages always outranks one that fails
earlier.  A PVT-feasible design, which has 45 units, outranks every infeasible
design.

## Within-tier violation

For measured evidence only, compute each constraint's maximum normalized
violation over started corners, then sum those maxima as
`partial_robust_violation`.  Invalid required status/measurement contributes
one for its constraint but never creates a synthetic physical value.

Within the same progress tier, lower partial robust violation is better.  The
canonical infeasible scalar supplied to optimizers is:

`1 + (45 - progress_units) + V_partial / (1 + V_partial)`.

It is at least 1, preserves the progress ordering, and uses the bounded final
term only within a tier.  Feasible feedback is
`worst_power / (power_limit + worst_power)`, which lies below 1.  Therefore the
overall ranking is exactly:

```text
PVT feasible > passed more corners/stages > failed earlier;
same tier: lower measured normalized violation;
feasible tie: lower worst-corner DC power.
```

The result also publishes the lexicographic tuple so the scalar can be audited.
No unmeasured corner is assigned an optimistic or pessimistic metric.

