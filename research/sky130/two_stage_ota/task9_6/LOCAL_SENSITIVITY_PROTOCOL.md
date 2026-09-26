# Frozen local robust-sensitivity protocol (Phase A)

This protocol was fixed using only the existing Task 9.5 negative Full-PVT
matrix, before any Task 9.6 sensitivity simulation. It does not alter the
Benchmark-v2 global 12-D search space or hard specifications. The exact
corner-selection calculation and all 15 baseline margins are preserved in
`near_corner_selection.json` (source matrix SHA-256
`5bab8f3d1a792f5e374ee66f9264b3bb419d67f6533a18551adf1044e4be9ad7`).

## Local candidate generation

Use the best 12/15 parameter vector from
`task9_5/feasibility/refinement_analysis.json`, with only a ≤4-ULP
representation overshoot at the compensation-capacitance upper bound
canonicalized and logged. Let `u=(x−low)/(high−low)` for linear parameters
and `u=(ln x−ln low)/(ln high−ln low)` for the frozen log-sampled parameters.
The 12 dimensions are perturbed independently, one at a time, by
`Δu ∈ {−0.02, −0.01, +0.01, +0.02}`: 48 unique local candidates. Thus the
percentages refer to the normalized *linear or log-coordinate range*, not
to a claim of equal physical-unit changes. Record original value, transformed
position, actual value/relative change, and the original search bound.

If baseline `u≤0.02`, use one-sided `+0.01,+0.02,+0.03,+0.04`; if
`u≥0.98`, use `−0.01,−0.02,−0.03,−0.04`. This applies in particular to the
upper-bound input-pair length and compensation capacitor. Mark
`boundary_limited=true`. Never clip an out-of-bounds proposal into the
boundary or simulate duplicate vectors. Canonical float roundoff is
recorded separately from an intentional perturbation. If unexpected
duplicated vectors occur after floating-point conversion, stop that
candidate and report rather than silently replacing it.

## Frozen near-constraint corners

For the baseline complete matrix, select a corner if it fails any frozen
hard constraint, **or** its minimum model-internal device-on or VDSAT
headroom margin is ≤0.01 V, **or** any measured normalized performance
hard-constraint slack is ≤0.02 (2%). This algorithm, including equality
at the threshold, is frozen before perturbations. It selects exactly five:

`tt__high_v_low_t`, `ss__high_v_low_t`, `fs__nominal`,
`fs__low_v_high_t`, `fs__high_v_low_t`.

The three failing corners cannot be dropped if later measurements shift.
Unselected corners are **UNKNOWN** for each local sensitivity candidate;
these 48 five-corner evaluations cannot establish Full-PVT feasibility or
exact robust violation.

## Measurements and analysis

Run OP, AC and transient independently on all five corners for every local
candidate (15 standard ngspice analyses each), plus one separate diagnostic
OP per corner to capture signed Id, `mirror` node and external coordinates
(5 more analyses). First run a fresh 45-analysis baseline; separate baseline
diagnostic probes are charged to the probe reserve. Missing/failed metrics
stay `null`, with error and cost recorded. For each variable, corner and
direction, report the signed change from the fresh baseline in:

- all seven role-wise model-internal `vgs−vth`, `vds−vdsat`, Id, gm, gds and
  floor-gated gm/Id, plus external signed and type-oriented voltages;
- gain, UGF, PM, power, output bias, positive and negative slew;
- stage nodes, branch-current evidence and each frozen hard-constraint
  status/normalized violation.

For the five selected corners, invoke the explicitly versioned Task 9.6
Benchmark-v2 boundary in `op_only` mode with those five corner IDs. The
underlying Task 9.5 v2 evaluator permits this subset only in `op_only` mode;
its `full` and `hierarchical` modes require all 15 corners and must **not**
be called with a five-corner subset. In Phase B, a separately versioned
local-diagnostic runner must execute the unchanged Task 9 real AC and
transient *stage measurements* for those same five corners and combine them
with the v2 OP classification. That runner is diagnostic-only: it may not
invoke the Task 9 v1 robust evaluator, label the result Full-PVT, or produce
`exact_robust_violation`. The five additional current/node OP probes use a
separate diagnostic instrument. All 20 processes per local candidate count
against the frozen budget.
All 48 outcomes are **partial** with respect to the 15-corner robust
objective. No optimizer-performance claim or post hoc corner selection is
permitted. Local finite differences show descriptive association, not a
unique causal mechanism.

## Boundary concentration and ranking

After Phase B, consider only the **top eight unique complete Full-PVT**
Task 9.6 candidates by exact robust violation, then worst-corner power,
then SHA-256 of canonical sorted parameter JSON. If fewer than eight exist,
use and report the actual number; do not fill with partial candidates.
The fresh baseline is eligible. For each variable compute normalized `u`
using the same linear/log rule; `u≤0.05` is near the lower 5%, `u≥0.95`
near the upper 5%. Report counts and raw parameter values. If only partial
candidates exist, make a separate, explicitly partial descriptive table,
never mix it into the exact ranking. Adaptive-sample concentration is
descriptive, not proof that a bound causes failure.
