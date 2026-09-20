# Task 9 PVT Evaluation Policy

Status: frozen before evaluator implementation, tests, smoke, or formal runs.

Version: `task9_safe_stage_and_corner_hierarchy_v1`

## Shared result semantics

Both policies use the same frozen benchmark, selected specification,
measurements, status validity, robust violation, PVT feasibility, and feasible
worst-power objective.  Each started corner stores process/VDD/temperature,
metrics, statuses, device evidence, errors, per-stage process time, and applied
condition checks.  Physical metrics for unrun stages/corners are null.

Every checkpoint binds candidate parameters, benchmark hash, policy hash,
corner-order hash, and completed corner/stage identities.  Resume begins at the
next missing stage; a completed ngspice call is never counted twice.

## `PVTFullEvaluationPolicy`

For every candidate, iterate the canonical 15-corner suite.  At every corner
attempt OP, AC, and transient in separate real ngspice processes, regardless of
prior stage or corner failure.  A failed process is isolated so remaining
analyses/corners are still attempted.  The result contains the complete PVT
metric/status matrix and is the reference truth.

## `PVTHierarchicalEvaluationPolicy`

Use the frozen static-worst-first corner order for every candidate.

Within each corner:

1. Run OP.  Continue only if operating region, power, and both output limits
   pass.  First-blocker priority is operating region, power, output low, output
   high.
2. Run AC only after OP passes.  Continue only if gain, UGF/status, and phase
   margin/status pass.  Priority is gain, UGF, phase margin.
3. Run transient only after OP and AC pass.  Positive- then negative-slew is the
   blocker priority.

Across corners, the first measured hard-constraint failure proves the logical
AND false and terminates the candidate.  No parameter heuristic, prediction,
learned model, surrogate, LLM, or adaptive corner choice can reject a candidate.
An invalid required measurement/status makes Full feasibility impossible and
is recorded as `analysis_failed`, not fabricated into a physical metric.  It
may terminate the candidate under the shared valid-measurement requirement but
is never described as a measured physics/specification rejection.

If all three stages pass at a corner, continue to the next corner.  Only after
all stages pass at all 15 corners is `pvt_feasible=true`.  Therefore no
Full-PVT-feasible candidate may be rejected early.

## Cost accounting

Per candidate record:

- candidate count;
- corners started and corners completed;
- OP, AC, transient, and total ngspice process calls;
- accumulated ngspice subprocess seconds;
- outer wall and orchestration seconds;
- first failing corner, stage, and constraint; and
- time-budget overshoot.

Primary cost is the sum of measured real subprocess elapsed seconds.  Full
always has 15 corner starts/completions and 45 process attempts.  Hierarchical
counts only actually launched processes.  Shadow-Full audit calls are separate
and never enter optimizer feedback or policy cost.

## Safe equivalence gates

Offline calibration replay must have 100% feasibility identity, zero false
acceptance, and zero false rejection.  Unit tests must include synthetic
positive and negative matrices.  Smoke hierarchical rejections are completed
with separate Full shadow work for identity audit.  Any false rejection stops
formal experiments without changing corners, thresholds, or policy.

