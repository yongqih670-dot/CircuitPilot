# Robust-feasibility diagnosis

## Result and scope

No real 15-corner PVT-feasible witness has been found for the frozen Task 9
12-dimensional global bounds and fixed 0.72 V tail bias under corrected
`model_consistent_saturation_v2` semantics. This is **not** a proof that the
feasible set is empty. No hard specification was weakened, no historical
result was overwritten, and no Task 10 formal experiment was started.

The Task 9.5 search was diagnosis only, not an optimizer comparison. Its
deterministic, pre-registered initial run logged 268 attempts, 68 fresh
complete 15-corner OP assessments and 1,820 ngspice OP processes. Targeted
in-bounds refinement logged a further 169 attempts, 37 fresh complete OP
assessments and 1,347 OP processes. Thus the two runs made 437 logged
attempts and 105 complete 15-corner OP assessments. None passed OP at all
15 corners, so none qualified for 45-analysis witness verification. A
separate, fresh complete 45-analysis matrix of the best candidate was run
for *negative characterization*, not as a positive witness.

All parameter vectors, exact outcomes, device quantities and costs are in
the three losslessly compressed, Git-tracked ledgers and
`feasibility/diagnostic_ledger_manifest.json`. Raw simulation inputs,
responses and logs are preserved locally in
`research_runs/task9_5_feasibility/` and an independently hashed ZIP (see
`EVIDENCE_ARCHIVE_MANIFEST.md`). The best design's full parameters are in
`feasibility/refinement_analysis.json`; its complete per-corner matrix is
`feasibility/full_characterization_matrix.json.gz`.

## Best observed in-bounds design

The best design passes all four OP hard constraints in 12/15 corners. A
separate fresh Full-PVT matrix performed all 45 processes, passed VDD and
temperature application checks in every corner, and had 12/15 corners
passing **all** OP/AC/transient hard constraints. Its v2 benchmark hash is
`8f622a92370e33ea6f608d7a31077096b8188b868dc070cebbf3ce67f9059708`.
It is infeasible. The Full-PVT matrix SHA-256 is
`5bab8f3d1a792f5e374ee66f9264b3bb419d67f6533a18551adf1044e4be9ad7`.

| Failing corner | Region-v2 device failures (VGS−VTH) | Other hard failure |
| --- | --- | --- |
| `ss__high_v_low_t` | first-stage load and mirror off, each −7.1 mV | None |
| `fs__nominal` | first-stage load and mirror off, each −10.2 mV | None |
| `fs__high_v_low_t` | input pair off, each −6.2 mV; first-stage load and mirror off, each −24.5 mV | Negative slew 488,748 V/s versus 500,000 V/s minimum (2.25% short) |

These devices had positive VDS−VDSAT headroom; the v2 *device-on* rule, not
drain headroom, is the active region failure in these three corners. All
15 corners passed the frozen gain, UGF, phase-margin, power and output-voltage
limits in this measured full matrix. Positive slew passed all 15; negative
slew failed only at the already region-invalid FS high-VDD/cold corner.
This makes process/temperature-sensitive input and first-stage load bias the
leading observed bottleneck, with a smaller coupled slew margin. It does not
exclude unobserved designs failing other metrics.

The best candidate is not a trivial search-bound pinning story: only
compensation capacitance and input-pair length are at their respective upper
bounds. Capacitance does not influence DC OP, so its bound cannot cause the
device-off OP failures. The input-pair length bound may matter for its own
FS/cold failure, but first-stage load length/width and other transistor
dimensions are interior, and the mirror remains off. A coupled geometry/bias
tradeoff remains plausible; this audit does not identify a single proven
infeasibility cause.

## Fixed-bias diagnostic outside the benchmark

With all 12 in-bounds parameters held at the best design, fresh 15-corner OP
at tail bias 0.60/0.64/0.68/0.72/0.76/0.80/0.84 V passed respectively
0/0/1/12/4/0/0 corners. These six non-0.72-V points are **outside** both the
historical benchmark and semantics-only Benchmark v2. This one-dimensional
sweep supplies no evidence that simply freeing the fixed tail bias would
solve the robust problem; 0.72 V was best among these seven sampled values.
It cannot establish a global optimum or rule out a coupled redesign.

## Benchmark/search-space implications

The v2 region rule changes hard classification and safe rejection, so future
corrected work must use the additive Benchmark v2 hash, never silently reuse
the Task 9 hash. But Benchmark v2 has **not** been shown solvable. No
search-space extension or specification change is adopted here. A future
proposal (e.g. coupled first-stage geometry/bias or a technology-legal input
length extension) requires its own pre-registered physical evidence, new
hash, full 45-run witness and positive hierarchical validation before any
formal Agent comparison. The current 437-attempt finite search and this
single-vector bias sweep do not justify claiming an empty feasible region.

The existing BO method is a **lightweight baseline**, not state-of-the-art
constrained Bayesian optimization. If formal optimizer comparisons are
eventually resumed, add a stronger non-LLM constrained optimizer or narrow
the comparative claim. These diagnostic searches and their budgets must
not be pooled into future optimizer superiority statistics.

## Positive safe-screening evidence

The hierarchical policy's rejection is logically safe *conditional on*
correct measured hard constraints: a measured failed OP or AC hard constraint
cannot be repaired by skipping later analyses for that same candidate.
Unit tests with synthetic positive 15-corner measurements confirm that the
v2 evaluator's Full and Hierarchical paths both accept a positive fixture.
Historical negative-only replay and these synthetic tests are **not** an
empirical positive-path validation for a real SKY130 witness. Because no
real witness exists, `PVT_FEASIBILITY_WITNESS.md` and
`POSITIVE_SCREENING_VALIDATION.md` are intentionally not created; a real
boundary-validation set remains required.
