# Research Task 6: Physics-Aware Staged Evaluation

## Outcome

Task 6 is complete and frozen. It adds a transparent, deterministic
operating-point screening policy around the immutable Task 5 SKY130
differential-amplifier benchmark and compares it with the unchanged Task 5
Full evaluator under Random, DE, TPE, and BO.

All pre-registered hypotheses meet their frozen decision rules:

| Hypothesis | Decision | Primary evidence |
|---|---|---|
| H1: expensive-analysis reduction | Supported | Formal A pooled paired median AC saving is 81.5%; paired bootstrap median 95% CI is 68.0% to 86.0%. |
| H2: cost-normalized feasibility search | Fully supported | Formal B pooled expensive-AC RMST is 34.74 for Screened versus 119.85 for Full, while success is 92.5% versus 70.0%. |
| H3: optimizer-dependent benefit | Supported descriptively | Method median AC-saving range is 38 percentage points and Spearman rho is 1.0. |

The result is deliberately narrow. Task 6 does not add an LLM agent, learned
failure classifier, adaptive search space, PVT optimization, mismatch Monte
Carlo, layout/parasitics, topology generation, or a new optimizer.

## Frozen identity

| Item | Frozen value |
|---|---|
| Task 5 benchmark SHA-256 | 57d2183621ecf37e5ca22e012452c43fce6459be7d347a5cfc93d0b394c14378 |
| Full policy SHA-256 | a07ea20ee7f16598602fa7f05218b45439e4bb87ac34c786d9881125372de0f0 |
| OP-Screened policy SHA-256 | 28110a5127748f185c35f038b2a4dcf333356ae54e676391042cebeff0cfe065 |
| Policy-family SHA-256 | 53b1eb73160b4d069135f406613cd1249fcdd002bfd6cb2b0c8892da1c3b4867 |
| Physics-rule SHA-256 | 704634265dcbc3e0e8a7dd56eb4bd07c385bf26b0ad4ce0f306bdc43401ce052 |
| Feedback-semantics SHA-256 | 2890448082b38377353526406abcd78cdca7b23f86d8a6765bbfb9f26bce3d27 |
| Cost-model SHA-256 | 1ddf380b35fa8f5628c10e1f6e25cf87a32ef336a4ce229d071a7b4d796d7726 |
| Formal A execution commit | 4740ac38af261c828307dd2d463a1a14d430eb77 |
| Formal B execution commit | 378f5482de403ecd0e05097bcc71e612249e7f52 |

Full is the unchanged Task 5 single-process OP plus combined differential and
common-mode AC path. Screened uses one explicit OP-only process, evaluates
versioned device-region and headroom rules, returns normalized transparent
constraint feedback for invalid candidates, and starts a second dual-AC
process only for OP-valid candidates. Rejected rows have no AC artifact and
their AC metrics remain null.

## Pre-registered designs

The pilot used 32 fixed paired candidates, randomized Full/OP-only order, and
64 real ngspice processes. It had zero failures, with 1 OP-valid and 31
OP-invalid candidates. OP-only was modestly cheaper: median outer wall time
0.563 s versus 0.610 s for Full. This justified retaining logical differential
plus common-mode AC count as the primary cost, with process calls and wall time
as mandatory secondary costs.

The frozen optimization designs were:

| Design | Cells | Per-cell stopping rule |
|---|---:|---|
| Post-fix smoke | 4 methods x 2 policies x 3 seeds = 24 | 25 candidates |
| Formal A, equal candidate | 4 x 2 x 10 = 80 | exactly 100 candidates |
| Formal B, equal expensive cost | 4 x 2 x 10 = 80 | 200 logical AC analyses or 300 candidates, whichever occurs first |

Formal A and Formal B both completed every cell with zero evaluation failures.
Their cross-suite fairness checks passed and bind every row to the hashes
above.

## Formal A: equal candidate count

Across 40 Full and 40 Screened runs, each policy evaluated exactly 4,000
candidates. Screened promoted 1,012 candidates to AC, rejected 2,988 at OP,
and used 2,024 logical AC analyses versus Full's 8,000, an aggregate reduction
of 74.7%. Because Screened starts an additional process for each promoted
candidate, process calls were 5,012 versus 4,000.

| Method | Full to Screened success | Screened OP rejection | Screened AC saving | Candidate RMST, Full to Screened | AC RMST, Full to Screened |
|---|---:|---:|---:|---:|---:|
| BO | 50% to 30% | 90.3% | 90.3% | 69.0 to 83.4 | 138.0 to 137.68 |
| DE | 100% to 90% | 69.6% | 69.6% | 31.5 to 50.8 | 63.0 to 37.2 |
| Random | 50% to 50% | 86.3% | 86.3% | 79.7 to 79.7 | 159.4 to 24.95 |
| TPE | 80% to 90% | 52.6% | 52.6% | 59.5 to 49.8 | 119.0 to 35.8 |

H1 is supported from the pre-registered paired percentage endpoint: the 40
method-seed pairs have median saving 81.5%, and the 10,000-resample paired
bootstrap median 95% interval is 68.0% to 86.0%.
The general paired-effects table also reports its bootstrap-mean interval
(69.625% to 79.6%) beside the raw differences, mean, and median; the
machine-readable H1 decision explicitly names and uses the median-resample
interval required by the H1 wording.

H3 is supported descriptively. Method-level paired median savings are BO
90%, Random 86%, DE 70%, and TPE 52%, giving a 38-point range. Their
association with method-level OP rejection rate has Spearman rho 1.0. This
association is partly structural rather than independent mechanistic evidence:
under the frozen accounting, each OP rejection avoids exactly two logical AC
analyses.

Formal A does not show an across-the-board feasibility advantage. Pooled run
success was 70% for Full and 65% for Screened. The policy changes feedback for
physics-invalid candidates, so adaptive optimizer sequences are expected to
diverge even though seeds, search space, optimizer configuration, and candidate
budget are paired and frozen.

## Formal B: equal expensive-AC budget

| Method | Full to Screened success | Full to Screened AC RMST | Screened candidates | Screened logical AC | Screened OP rejected |
|---|---:|---:|---:|---:|---:|
| BO | 50% to 90% | 138.0 to 49.0 | 3,000 | 798 | 2,601 |
| DE | 100% to 100% | 63.0 to 26.4 | 2,435 | 2,000 | 1,435 |
| Random | 50% to 80% | 159.4 to 61.0 | 3,000 | 762 | 2,619 |
| TPE | 80% to 100% | 119.0 to 36.8 | 1,777 | 2,000 | 777 |
| Pooled | 70.0% to 92.5% | 119.85 to 34.74 | 10,212 | 5,560 | 7,432 |

Pooled expensive-AC Kaplan-Meier median time to feasible fell from 114 to 24
logical analyses. The pooled RMST at the common 200-AC horizon fell from
119.85 to 34.74, while observed feasibility rose from 28/40 to 37/40 runs.
Both H2 conditions therefore hold and H2 is fully supported.

The candidate-count secondary endpoint is more nuanced. Screened evaluates
more candidates per logical AC: 10,212 versus 4,000 total. At the 300-candidate
horizon, pooled candidate RMST is 100.72 for Screened versus 119.93 for Full,
but the candidate Kaplan-Meier median is 66 versus 57. BO and Random reached
the 300-candidate cap in all seeds before consuming the 200-AC allowance; DE
and TPE reached the AC allowance.

## Physical rejection taxonomy

Formal B Screened classified 7,432 of 10,212 candidates as physics-invalid.
A candidate may carry multiple rule labels, so category counts are not
mutually exclusive.

| Violation | Count | All-candidate rate | Invalid-conditional rate |
|---|---:|---:|---:|
| tail_not_saturated | 3,637 | 35.61% | 48.94% |
| input_pair_off | 3,570 | 34.96% | 48.03% |
| multiple_physics_violations | 2,789 | 27.31% | 37.53% |
| active_load_off | 2,282 | 22.35% | 30.71% |
| tail_off | 1,477 | 14.46% | 19.87% |
| output_headroom_invalid | 303 | 2.97% | 4.08% |
| input_pair_not_saturated | 257 | 2.52% | 3.46% |

The published violation-by-iteration table and plots retain the method and
policy breakdown instead of collapsing these distributions into a learned
classifier.

## Wall-time and process-cost finding

Logical AC reduction did not translate into wall-clock reduction on this
Windows host. In Formal B, Screened launched 12,992 ngspice processes versus
4,000 for Full and accumulated 10,629.34 s of terminal runtime versus
3,138.54 s. Median wall time to first observed feasible result was 60.34 s
versus 29.98 s. The paired terminal-runtime difference, Screened minus Full,
had median +182.50 s with percentile 95% interval +172.17 s to +202.46 s.

This is consistent with the pre-registered pilot: for this small circuit,
ngspice startup and SKY130 model loading dominate. The primary result is
therefore an expensive-analysis result, not a claim of wall-clock acceleration.
Wall-time comparisons are descriptive because the four method suites were
scheduled concurrently.

## Implementation and recovery guarantees

Task 6 adds:

- immutable protocol and semantic hashing for Full, Screened, physics rules,
  normalized feedback, and the exact cost model;
- explicit candidate, process, OP, differential-AC, common-mode-AC, promoted,
  rejected, logical-AC, and physical-analysis counters;
- SQLite plus atomic CSV evidence, per-candidate stage/status/taxonomy, raw
  metrics, cumulative costs, event times, and optimizer checkpoints;
- cell-level suite resume with exact candidate replay when SQLite is one
  committed row ahead of an optimizer checkpoint;
- fairness rejection for incomplete cells, identity drift, budget drift, or
  policy-specific cost-accounting drift;
- Kaplan-Meier coordinates, RMST, paired effects, 10,000-resample confidence
  intervals, violation distributions, plots, and machine-readable H1-H3
  decisions.

Two rejected execution attempts are fully disclosed in
[task6/EXECUTION_INCIDENTS.md](task6/EXECUTION_INCIDENTS.md). The first exposed
a Windows process-global SUBST race and led to an isolated ASCII runtime with
a content-addressed cache of the exact frozen model fragments. The second
exposed a transient CSV replacement denial and led to bounded replacement
retries plus exact optimizer-state replay. Both rejected roots were deleted
before the accepted reruns and no rejected row enters the statistics.

## Verification

Final repository regression:

- 239 tests passed;
- 1 unrelated environment-dependent Task 3 test skipped because
  SKY130_MODEL_LIBRARY was not configured;
- all Task 6 unit and real-ngspice integration tests passed;
- post-fix smoke: 24 runs, 600 candidates, 642 processes, 684 logical AC
  analyses, zero failures, two feasible runs, fairness passed;
- Formal A: 80/80 cells, zero failures, fairness passed;
- Formal B: 80/80 cells, zero failures, fairness passed;
- 24 raw-evidence archives and the complete publication hash index were
  independently rehashed with zero mismatches.

## Evidence and reproducibility

Primary publication entry points:

- [Combined machine-readable decisions](task6/results/combined/statistics/hypothesis_decisions.json)
- [Combined group summary](task6/results/combined/statistics/group_summary.csv)
- [Combined paired effects](task6/results/combined/statistics/paired_effects.csv)
- [Combined survival coordinates](task6/results/combined/statistics/survival.csv)
- [Combined violation distribution](task6/results/combined/statistics/violation_distribution.csv)
- [Formal A fairness proof](task6/results/formal_equal_candidate/fairness_validation.json)
- [Formal B fairness proof](task6/results/formal_equal_cost/fairness_validation.json)
- [Raw-evidence manifest](task6/results/evidence_manifest.json)
- [Complete SHA-256 index](task6/results/file_hashes.json)
- [Related-method positioning](task6/RELATED_METHOD_POSITIONING.md)

The results directory contains 24 ZIP archives split by design, method, and
policy. They retain every accepted run's candidate CSV, SQLite database,
configuration, manifest, summary, optimizer checkpoint, generated netlists,
ngspice logs, and raw data. The published tree is 166.55 MiB and its largest
file is 15.19 MiB.

The accepted suite paths and execution commits are preserved in each design's
accepted_suites.json and provenance directory. Reanalysis is performed with:

    python scripts/finalize_task6.py \
      --formal-a-suite <one accepted suite per method> \
      --formal-b-suite <one accepted suite per method> \
      --smoke-suite <accepted post-fix smoke suite>

The finalizer rejects incomplete or hash-drifted suites, reruns combined
fairness validation, regenerates all tables and plots, packages raw evidence,
and writes SHA-256 for every published file.

## Related methods and limits

[task6/RELATED_METHOD_POSITIONING.md](task6/RELATED_METHOD_POSITIONING.md)
compares this study with constrained Bayesian optimization, multi-fidelity BO,
TuRBO, simulation-efficient analog sizing, AutoCkt, and post-layout sizing.
Task 6 is best described as an audited deterministic staged evaluator, not as
a learned constraint model or general multi-fidelity optimizer.

External validity is limited to one five-transistor topology, one frozen
search space, SKY130 TT at 27 C, schematic-level simulation, four optimizers,
and ten paired seeds. No claim is made about other PDKs, PVT corners, mismatch
yield, post-layout behavior, larger topologies, or production wall-clock
speedup.
