# Frozen exact-versus-partial feedback semantics (Phase A)

This protocol applies only to corrected Benchmark v2
`8f622a92370e33ea6f608d7a31077096b8188b868dc070cebbf3ce67f9059708`
and `model_consistent_saturation_v2`. Task 9's historical v1 evaluator and
`task9_protocol.partial_feedback` are not Task 9.6 corrected-search APIs.

## Exact robust violation

An exact result requires an independently measured, complete 15-corner
matrix with OP, AC, and transient in every corner (45 analyses), no analysis
error, and passing VDD/temperature application checks. For each frozen hard
constraint `k`, evaluate Task 9's unchanged normalized per-corner component
`c[k,corner] >= 0`; define `C[k] = max_corner c[k,corner]` and
`exact_robust_violation = sum_k C[k]`. Only a fresh **Full-PVT** run is
eligible for final candidate ranking, witness declaration or Task 10 guard.
If any required measurement is missing/invalid, `exact_robust_violation`
is JSON `null`, not zero. An all-45-analysis Hierarchical run is useful for
positive screening validation but still requires a separate fresh Full-PVT
matrix for final ranking and existence proof.

## Partial measured feedback

An early-stopped Hierarchical or OP-only candidate has
`robust_evaluation_status = "partial"`. Every unmeasured corner, stage,
metric and constraint component remains `null`/`UNKNOWN`; it is never
filled with 0, PASS, or an inferred value. Analysis errors and failed corner
application checks are explicit invalid measured outcomes, not missing
successes. For each constraint with at least one actual stage measurement,
record `L[k] = max(measured c[k,corner])`; when no such stage was measured,
record `L[k] = null`. The nonnegative sum of available `L[k]` values is a
**measured robust-violation lower bound**, not the exact robust violation.
If nothing was measured, that lower bound is also `null`.
Any measured analysis error or failed application check makes a proposal
`partial_search_score.eligible = false`; it is retained in the ledger and
budget, but cannot be promoted on a fictitious low violation. A separately
logged, budgeted retry may produce a new evaluation; it does not erase the
failed attempt.

`partial_search_score` is a structured diagnostic ordering key:

1. More passed measured stages (0--45) is better.
2. More fully passed measured corners (0--15) is better.
3. Smaller measured robust-violation lower bound is better.
4. Smaller device margin penalty is better; for every measured OP device,
   add `max(0, -on_margin_V)/0.01 + max(0, -vdsat_headroom_V)/0.01`.
5. Resolve remaining ties by the lexicographic SHA-256 hash of the exact
   JSON-serialized parameter vector.

The implementation represents this as a tuple/order key, with explicit
named components, not a misleading single robust-violation number.
It guides proposals and the preregistered, method-blind promotion of at most
eight distinct candidates to Full-PVT. It is **not** used for final robust
ranking or a success declaration. Scores with different measured coverage
are inherently incomparable as physical exact objectives; the progress-first
ordering is only a proposal heuristic.

Final `best_exact_candidate` and boundary-concentration analyses use only
unique complete Full-PVT matrices ranked by exact violation, then worst
measured power, then parameter hash. If none exists, report only
`best_partial_candidate` with its coverage and unknowns. No claim of
PVT feasibility can follow from a partial result even if every measured
component is zero.
