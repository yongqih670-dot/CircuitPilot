# Research Task 9: PVT-Robust Hierarchical Optimization

## Executive conclusion

Task 9 implemented and audited a deterministic, exact-feasibility-preserving
PVT evaluation baseline for the frozen SKY130 two-stage OTA.  It combines
within-corner `OP -> AC -> transient` gating with across-corner short-circuiting
after, and only after, a completed physical measurement proves a frozen hard
constraint violation.  It never predicts an unrun metric; every unrun physical
field remains null.

The safety and efficiency conclusions are positive, but the robust-optimization
conclusion is deliberately negative.  Replay preserved Full-PVT feasibility for
64/64 calibration matrices with zero false acceptance and zero false rejection,
and the smoke shadow audit found zero false rejection in 120 candidates.  Under
the equal-candidate experiment, Hierarchical-PVT saved a median 97.87% of
accumulated ngspice time (paired bootstrap 95% CI for the mean:
97.90%--98.06%).  However, no formal run found a design satisfying all hard
constraints at all 15 corners.  Under the primary equal-simulator-time design,
both policies had 0/40 successful runs and identical pooled accumulated-time
RMST.  Therefore H4 is not supported: higher candidate throughput is not
evidence of improved robust feasibility.

## Frozen ancestry and identities

Task 9 added new PVT artifacts without changing Task 7 or Task 8 topology,
search space, PDK, nominal measurements, feasibility definitions, raw results,
or protocol identities.  The freeze audit started from commit
`fbe0d023555f715dd47fa4af6826316e10cdd3bf`.

- Task 7 benchmark hash:
  `144100e168ca5f550c6ca0bd5a29788f669d0e34cd9008c5a7fe2099e8cb8c1c`
- Task 8 protocol hash:
  `d60ad33791a59bf418b0378e653e4e3bc10aa032dc98cde583d649260844dc2d`
- Frozen Task 7 YAML byte hash:
  `077a42c053dfa59b6deb6e19dbca6cd74bec8122ebcb17998b906a4aa590df28`
- Frozen Task 8 manifest byte hash:
  `9ca7caf490338683aad3d5ef6f50d87427130e9c3b95c8e3f227d44dc070d053`

The full byte-level inventory is in `TASK7_TASK8_FREEZE_AUDIT.md` and is
recomputed by the regression suite.

## Real PVT capability and frozen suite

The installed Open_PDKs SKY130A model tree was parsed rather than assumed.  It
contains 51 top-level sections.  The five non-mismatch MOS process choices used
here--TT, SS, FF, FS, and SF--have real NFET and PFET primitive fragments.  The
PDK identity is Open_PDKs `1.0.606`, commit
`026824c7969ce6f4fc9678e6ca04b0a06a596c4b`; the complete model-tree SHA-256 is
`d88fa42b4f42f7b1f6987141aa92161865cfc9ff5fbdce9bbc9f137bde3a2f61`.

All five process choices executed successfully in real ngspice at three
predefined electrical conditions: 1.80 V/27 C, 1.62 V/125 C, and 1.98 V/-40 C.
All 15 probes matched requested VDD and temperature within `1e-9`, and changing
the process fragments changed measured device characteristics.  No missing
corner was aliased or synthesized.  The 1.98 V point is an audited simulation
condition, not a foundry lifetime qualification.

The frozen suite is the full 5 x 3 Cartesian product, for 15 corners.  FS/SF
are included because this OTA has both NFET and PFET signal paths; mismatch and
Monte Carlo sections are out of scope; passive-only sections do not alter this
benchmark's ideal capacitors and absent modeled resistors/interconnect.  The
corner-suite hash is
`a97a333a89b5d709714e21e0a5497656fdbcc9168065f1113820a7513e013096`.

PVT feasibility is an exact logical AND: every required measurement must be
valid and every hard constraint must pass at every corner.  Robust violation is
the sum, over constraints, of each constraint's maximum normalized corner
violation.  Feasible designs minimize worst-corner DC power as the frozen
secondary objective.  Each metric retains its own worst corner; no physically
meaningless universal worst corner is constructed.

## Nominal-to-PVT gap, calibration, and benchmark freeze

All 27 unique saved Task 7/8 nominal-feasible designs were re-evaluated with a
complete 15-corner matrix.  None remained PVT feasible: 0/27 PVT feasible and
27/27 nominal-feasible-but-PVT-failed.  This required 405 OP, 405 AC, and 405
transient analyses (1,215 ngspice processes) with zero analysis errors.  The
complete matrix hash is
`224c1cfcb9e172facadf116ae4461660adcd022e74e33e16473d219b6db5eab7`.

An independent preregistered Sobol set of 64 candidates, hash
`8243cf5a1c9ee19df284976b7e0d9d985f0fe6d7a851ed8446cad6c398983902`,
was evaluated with Full-PVT before optimizer experiments.  All five frozen
specification-ladder rows produced 0/64 robust-feasible designs, so the target
0.1%--2.0% density band was missed.  The preregistered equal-distance/stricter
row tie break mechanically selected row 0, the exact Task 7 thresholds; no
threshold was changed or interpolated.  No calibration design had all 15
corners operating-region valid, explaining why numerical relaxation did not
change density.  The selected-specification hash is
`05b5c71863b852dc758cfed7643ace6aa9f6a7636856bf1eb09addef77681748`.

The median complete Full-PVT calibration cost was 37.5415 accumulated ngspice
seconds.  The frozen mechanical budget rule selected 20 candidates per formal
equal-candidate cell, 375.415 seconds per equal-time cell, a 100-candidate cap,
and 10 candidates per smoke cell.

The complete Task 9 protocol was frozen before implementation and optimizer
experiments:

- PVT benchmark hash:
  `ec2d4de0e0c5694598cc7444b4fa9b63a8d8b533fa68bdd504e5262ebd5e2d61`
- Task 9 protocol hash:
  `feae5ad0f0b234814d36b567be9b5952934617a3ff3745983a0249fe38c7963b`
- evaluation-policy hash:
  `6d63ca8809ec9afdfaad2e681c70ea4a189cfd5b48ff749757dfe883ef8b55a4`
- partial-feedback hash:
  `dd0063c0cc3c8e44c73a5607f3e8361162521f26c5d6ff40032ea81471f61fda`

## Policies, corner order, and safety audits

Full-PVT runs OP, AC, and transient at all 15 corners even after a failure,
yielding a complete reference matrix.  Hierarchical-PVT uses the same physical
testbenches and constraints but gates OP -> AC -> transient within each corner,
then stops the candidate across corners as soon as a real completed analysis
proves a hard failure.  Partial feedback contains only measured corners and
measured violations.  Unrun stages/corners are null and never imputed.

The fixed formal corner order was derived once from the complete Sobol64
matrix using the preregistered rejection-frequency, severity, runtime, and
canonical-index tie rules:

`sf__nominal`, `ss__low_v_high_t`, `tt__low_v_high_t`,
`ff__low_v_high_t`, `ss__nominal`, `tt__nominal`, `ff__nominal`,
`ss__high_v_low_t`, `fs__low_v_high_t`, `tt__high_v_low_t`,
`fs__nominal`, `fs__high_v_low_t`, `sf__low_v_high_t`,
`sf__high_v_low_t`, `ff__high_v_low_t`.

Its hash is
`e07c17b9041c271e15d49d3362253db3a21fcd6eede169158dd18c7bb975fc56`.
It is identical for every candidate and is not an adaptive predictor.

Offline replay over all 64 complete calibration matrices produced 64/64
feasibility identity for both nominal-first and static-worst-first orders, with
zero false PVT acceptances and zero false PVT rejections.  Static-worst-first
avoided 896 corners, 896 OP, 959 AC, 960 transient, and 2,815 process calls,
saving 2,351.176 simulator seconds (97.7%).  The calibration set had no positive
PVT-feasible case, so positive-path safety was additionally enforced in unit
tests and checked by the smoke shadow-Full audit.

## Smoke validation

Smoke covered Random, DE, TPE, and BO; both policies; seeds 0--2; and 10
candidates per cell (24 cells, 240 primary candidates).  It passed corner/model
switching, voltage/temperature application, stage gates, accounting, resume,
evidence, and paired-fairness checks with zero analysis errors.  The 120
Hierarchical-PVT candidates had zero shadow-Full false rejections.  Neither
policy found a PVT-feasible design; smoke is validation evidence only and is
not used for algorithmic claims.

| Smoke policy | Candidates | Corners started | OP | AC | Transient | Processes | ngspice s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full-PVT | 120 | 1,800 | 1,800 | 1,800 | 1,800 | 5,400 | 4,505.927 |
| Hierarchical-PVT | 120 | 121 | 121 | 1 | 1 | 123 | 102.308 |

## Formal experiment A: equal candidate budget

The 80 paired cells comprise four methods, two policies, seeds 0--9, and 20
candidates per cell.  Each policy completed 800 candidates.  Both policies
found 0 PVT-feasible candidates and 0/40 successful runs.

| Policy | Candidates | Corners started/completed | OP | AC | Transient | Processes | ngspice s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full-PVT | 800 | 12,000 / 12,000 | 12,000 | 12,000 | 12,000 | 36,000 | 27,598.029 |
| Hierarchical-PVT | 800 | 803 / 7 | 803 | 9 | 7 | 819 | 548.954 |

Across the 40 method+seed pairs, Hierarchical-PVT saved a median 280 corners,
280 OP calls, 300 AC calls, 300 transient calls, and 880 process calls per
cell.  Paired bootstrap mean savings and 95% CIs were respectively 279.925
[279.825, 280.000] corners, 279.925 [279.825, 280.000] OP, 299.775
[299.650, 299.900] AC, 299.825 [299.700, 299.925] transient, and 879.525
[879.200, 879.800] processes.  Median simulator time saved was 631.1335 s;
the mean was 676.2269 s [649.4676, 703.9445].  Median percentage saving was
97.8705%; the mean was 97.9818% [97.9046%, 98.0599%].

## Formal experiment B: equal simulator-time budget

This is the primary efficiency experiment: 80 paired cells, 375.415 accumulated
ngspice seconds per cell, and a 100-candidate cap.  The runner checks the budget
immediately after each completed OP, AC, or transient analysis and never kills
a running ngspice process.  A completed analysis may overshoot the budget; the
maximum observed overshoot was 0.932 s.

| Policy | Candidate records | Completed / terminal | Corners started/completed | OP | AC | Transient | Processes | ngspice s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Full-PVT | 386 | 346 / 40 | 5,427 / 5,397 | 5,427 | 5,409 | 5,397 | 16,233 | 15,036.894 |
| Hierarchical-PVT | 4,000 | 4,000 / 0 | 4,038 / 68 | 4,038 | 86 | 68 | 4,192 | 3,848.740 |

Each Full-PVT cell ends with one explicitly marked partial terminal candidate;
its completed analyses count toward the time budget, but its incomplete
physical record is not returned to the optimizer and is excluded from complete
Full-matrix descriptive statistics.  All Hierarchical-PVT cells reached the
100-candidate cap.  Despite the throughput difference, both policies had 0/40
PVT-successful runs.

An implementation audit detected that an earlier provisional run checked the
budget only at candidate boundaries.  That output was moved to an ignored
`task9_equal_time_candidate_terminal_invalid_20260921` directory and is absent
from every statistic and evidence hash in this report.  The experiment was
rerun from scratch with the frozen analysis-level rule; only the strict rerun
is reported here.

## Robust time-to-feasible and hypothesis tests

No formal run observed the first-PVT-feasible event, so every KM curve is fully
censored and no KM median exists.  Candidate, corner, OP, AC, transient, and
accumulated-ngspice-time curves and RMST tables are nevertheless exported as
preregistered.  At the pooled equal-time shared horizons, both policies have
identical RMST because neither has an event:

| Axis | Shared horizon | Full RMST | Hierarchical RMST | Events (Full/Hier.) |
|---|---:|---:|---:|---:|
| Candidate | 10 | 10 | 10 | 0 / 0 |
| Corners started | 106 | 106 | 106 | 0 / 0 |
| OP calls | 106 | 106 | 106 | 0 / 0 |
| AC calls | 9 | 9 | 9 | 0 / 0 |
| Transient calls | 9 | 9 | 9 | 0 / 0 |
| Accumulated ngspice seconds | 113.471 | 113.471 | 113.471 | 0 / 0 |

For the primary accumulated-time endpoint, Full minus Hierarchical pooled RMST
is 0.0 s with a 10,000-resample paired bootstrap 95% CI of [0.0, 0.0].  This is
not evidence of equivalence beyond the observed horizon; it is the consequence
of complete censoring.

Preregistered decisions are:

- **H1 supported:** replay identity was exact and smoke shadow false rejections
  were zero.
- **H2 supported:** corners, AC, transient, and process calls were reduced with
  positive paired effects and CIs.
- **H3 supported:** accumulated ngspice time fell substantially under equal
  candidate budgets.
- **H4 not supported:** equal-time success was 0/40 for both policies and the
  primary RMST difference was zero.
- **H5 supported:** all 27 nominal-feasible designs failed the frozen PVT suite.

## Worst-corner and robustness-failure characterization

Worst-corner distributions use complete Full-PVT matrices only: 800
equal-candidate designs and 346 completed equal-time designs.  The most common
worst corner for each metric was:

| Metric | Equal-candidate top corner (count/800) | Equal-time top corner (count/346) |
|---|---|---|
| Gain | `sf__low_v_high_t` (319) | `sf__low_v_high_t` (139) |
| UGF | `fs__high_v_low_t` (347) | `fs__high_v_low_t` (140) |
| Phase margin | unavailable (215) | unavailable (107) |
| Power | `ff__high_v_low_t` (289) | `sf__low_v_high_t` (116) |
| Positive slew | `fs__high_v_low_t` (251) | unavailable (96) |
| Negative slew | `fs__high_v_low_t` (390) | `fs__high_v_low_t` (155) |
| Output margin | `sf__high_v_low_t` (260) | `sf__high_v_low_t` (111) |

“Unavailable” is retained as an explicit evidence state when the required
metric cannot validly define a worst corner; it is not silently replaced.  In
nominal-first replay, the first failure was `tt__nominal` for every complete
matrix.  In static-worst-first replay it was `sf__nominal` for 797/800 and
345/346 matrices, with the remainder first failing at `ss__low_v_high_t`.

The multilabel failure taxonomy shows that every complete matrix had a process
corner failure, low-voltage failure, high-temperature failure, and an
operating-region failure.  Under equal-candidate Full-PVT, 795/800 had multiple
constraint failures, 782 output-bias, 658 negative-slew, 639 positive-slew,
587 phase-margin, 585 UGF, 565 gain, and 22 power failures.  The corresponding
equal-time complete-matrix counts were 343/346 multiple, 340 output-bias, 288
negative-slew, 287 positive-slew, 258 phase-margin, 264 UGF, 263 gain, and 9
power failures.  These counts are descriptive and multilabel; they do not sum
to the number of designs.

## Evidence integrity and reproducibility

All 24 smoke cells and all 80 cells in each formal design passed paired
fairness validation.  Consolidated Formal A evidence is
`results/equal_candidate/evaluations.csv`, SHA-256
`027a0d6de4f956e90cd0254b331394a2e6105d2942dcdfd8259a6afe27690dd2`.
The larger strict Formal B evidence is losslessly and deterministically gzip
compressed as `results/equal_simulation_time/evaluations.csv.gz`, SHA-256
`b1124da28a6b924e728c4d029a2b04b682e5eb306923e785454613342648f4b1`.
Its decompressed CSV has 4,387 rows including the header and SHA-256
`4436ad848ccf8ddc758078eb8797d2ac7d34d2e3ecc3da106405384d3db82ff9`.

Machine-readable conclusions are in `results/task9_summary.json`; paired
effects, KM curves, RMST, worst-corner distributions, first failures, and the
taxonomy are in `results/statistics/`.  Raw per-cell run directories are local
checkpoint evidence and intentionally ignored; tracked consolidated artifacts
are the publication evidence.

## Limitations and Task 10 recommendation

This study covers one topology, one open PDK/model installation, 15 discrete
deterministic corners, and no mismatch, layout parasitics, aging, topology
generation, learned surrogate, or adaptive order.  The calibration target was
not achieved, all formal survival data are censored, and operating-region
failure dominates.  The data establish safety and cost reduction, not that the
search methods can solve this robust benchmark.  They also do not establish
superiority over published PVT-aware learning or progressive-corner methods.

Task 10 should keep this exact benchmark, hashes, safety oracle, and Full-PVT
shadow audit, then target the observed bottleneck rather than weaken the
robustness definition.  A suitable next step is a constrained, auditable
PVT-aware search/Agent that improves operating-region discovery and static-order
throughput under the same accumulated-time budget.  Any learned ordering or
surrogate should be allowed to prioritize evaluation, but it must not declare
feasibility or skip a candidate permanently without eventual exact 15-corner
verification.  The decisive comparison should remain paired time-to-first
PVT-feasible under the unchanged Task 9 suite, with false rejection fixed at
zero and Full-PVT confirmation of every reported success.
