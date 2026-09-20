# Task 9 PVT Calibration and Difficulty Protocol

Status: pre-registered after the nominal-to-PVT gap and before generation or
evaluation of any calibration candidate.

Version: `task9_sobol64_full_pvt_calibration_v1`

## Permitted input from earlier steps

The only observed Task 9 result used to set calibration cost is the independent
nominal-gap Full-PVT runtime: median 37.598 accumulated ngspice seconds per
candidate (27 candidates, 15 corners, 45 processes each).  Nominal-gap metrics,
failures, and corner frequencies do not select the Sobol candidates, ladder
row, corner order, or formal budget.

## Calibration sample-size rule

Before calibration candidate generation, freeze this runtime rule:

- if the independent median Full-PVT time is at most 25 s, use 128 candidates;
- otherwise use 64 candidates.

The observed 37.598 s therefore mechanically selects **64 candidates**, within
the requested 64--128 range.  This decision is immutable even if calibration
runs faster or slower.

## Independent candidate set

- Generator: `scipy.stats.qmc.Sobol`
- Dimensions: the unchanged 12 Task 7 search dimensions
- Scrambling: enabled
- Seed: `9200901`
- Sample operation: `random_base2(m=6)`, producing exactly 64 points
- Decode: frozen Task 7 `decode_unit_candidate`, including its linear/log rules
- Optimizer feedback: none
- Duplicates: impossible in Sobol unit coordinates; decoded candidates are
  asserted unique and any violation halts calibration

The unit coordinates, decoded values, generator/library version, and candidate
set hash are saved before simulations begin.  Random, DE, TPE, BO, prior formal
results, and adaptive sampling are forbidden inputs.

## Evaluation

Every calibration candidate uses Full-PVT in canonical suite order.  Every one
of the 15 corners independently attempts OP, AC, and transient even after any
failure.  Thus each completed candidate has 15 corner rows and 45 real ngspice
process attempts.  Per-corner metrics, statuses, constraint components,
operating-region evidence, process time, VDD check, and temperature checks are
retained.  Errors or missing required values count as real infeasibility and
are reported, never imputed.

## Mechanical specification selection

Apply every row of the already frozen `PVT_SPECIFICATION_LADDER.yaml` to the
same completed 64-candidate Full-PVT matrices.  A candidate is robust feasible
only if all 15 corners pass every constraint and required status for that row.

The target closed density band is 0.1%--2.0%.  With 64 candidates, exactly one
feasible candidate (1.5625%) lies in the band.  Select the lowest row index in
the band.  If no row lies in the band, select the row whose density has minimum
distance to the closed band; ties select the lower, stricter row index.  No
threshold may be interpolated or added.  Operating-region validity and valid
measurements are invariant across all rows.

## Corner statistics

Using the selected row, report for each corner:

- candidate rejection count and fraction (any hard failure at that corner);
- each constraint's failure count and fraction;
- mean and median total normalized corner violation;
- mean, median, and total OP/AC/transient/process runtime;
- the nominal-first replay first-failure count and probability; and
- metric severity summaries without collapsing different physical metrics.

These are complete-matrix descriptive statistics; no candidate is censored by
an evaluation order.

## Static worst-first order

Sort all 15 corners once using this lexicographic key:

1. rejection fraction, descending;
2. mean total normalized corner violation, descending;
3. mean accumulated ngspice seconds for the complete corner, ascending;
4. rank in the frozen `NOMINAL_FIRST_ORDER`, ascending; then
5. `corner_id`, ascending.

All quantities come from the selected-row Full-PVT calibration matrix.  Exact
unrounded binary floating-point values drive sorting; published tables may be
rounded.  The resulting `STATIC_WORST_FIRST_ORDER` and its canonical SHA-256
are frozen before replay, implementation, smoke, or optimizer experiments.
Static worst-first is the formal Hierarchical-PVT order.  Nominal-first is kept
only for descriptive replay/cost comparison.  There is no per-candidate or
online reorder.

## Replay rule and integrity gate

Offline replay both frozen orders over every complete calibration matrix.
Within a corner, apply OP, then AC only after OP constraints pass, then
transient only after AC constraints pass.  Across corners, stop only after a
real measured hard failure.  Compare final PVT feasibility against Full-PVT.

Replay must report exactly zero false acceptance and zero false rejection for
both orders and 100% feasibility identity.  It also reports corners, OP, AC,
transient, process calls, and accumulated ngspice seconds avoided.  Any identity
failure halts Task 9 before benchmark freeze.

## Formal-budget rules

After calibration, use its median completed-candidate accumulated ngspice time
to choose the equal-candidate budget:

- at most 20 s: 50 candidates;
- more than 20 s and at most 30 s: 30 candidates;
- more than 30 s: 20 candidates.

For the equal-simulator-time experiment, use `10 × calibration median
Full-PVT candidate accumulated ngspice seconds` for every method/policy cell.
Set the candidate cap to `5 × equal-candidate budget`.  Check the budget only
after a completed analysis, retain the overshoot, and never kill ngspice
mid-process.  Smoke uses exactly 10 candidates for each method/policy/seed cell.
These rules cannot change after optimizer behavior is observed.

