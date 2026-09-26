# Task 9.6 PVT feasibility diagnosis — final report

**Decision B.** No real Benchmark-v2 15/15 PVT-feasible OTA was found
within the frozen Phase-B plan. This is not proof of v2 infeasibility.
Task 10 remains machine-blocked; v3 remains an unimplemented proposal.

## Integrity, version and objective semantics

Tasks 6–9.5 remain byte-identical under `history_freeze.json`.
The Task 6 RMST wording addendum distinguishes genuine positive-tail
extrapolation on the candidate-count axis from conservative common
truncation at 92 AC calls; Full did have observations through 200 AC.
Every corrected candidate-level Full/Hierarchical search evaluation
called the explicit Task 9.5 `model_consistent_saturation_v2`
evaluator under hash `8f622a92370e33ea6f608d7a31077096b8188b868dc070cebbf3ce67f9059708`.
The five-corner diagnostic path called that v2 evaluator for OP-only
classification, then reused the unchanged physical AC/transient stage
measurement functions; it never called the Task 9 v1 robust evaluator
or used the old v1 hash as corrected semantics.
Only fresh 15×(OP+AC+transient) Full matrices produce exact robust
violation. The 96 Hierarchical search results retain unmeasured stages
as UNKNOWN and use a separate partial proposal ordering; zero measured
violation is not a feasibility claim.

## Preregistered and actual budget

The frozen plan capped 6,500 ngspice processes, 6,000 accumulated
simulator seconds and ten wall-clock hours, with stricter per-activity
allocations. Search was capped at 64 seeded DE + 32 seeded local
proposals, eight method-blind Full promotions and six-neighbor
validation only after a positive witness. The plan was not extended.

| Activity | Actual ngspice processes |
| --- | ---: |
| `device_audit_probes` | 5 |
| `failed_analysis_retry_reserve` | 0 |
| `fresh_baseline_full` | 45 |
| `fresh_witness_full_confirmation` | 0 |
| `full_promotion_8_candidates` | 360 |
| `hierarchical_search_96_candidates` | 225 |
| `positive_hierarchical_validation` | 0 |
| `sensitivity_48_candidates` | 960 |
| `six_neighbor_full_and_hierarchical` | 0 |
| **Total** | **1595** |

Accumulated measured/charged simulator time: **884.869 s**.
All 1,595 starts have finishes and every ngspice process returned success;
no retry or analysis-error process was charged. The search stopped when
both the 96-candidate and eight-promotion caps were reached, not because
the larger global process/time ceilings were exhausted. No extra run
was made to consume unused allowance.

## Device-on, bias and coordinate diagnosis

`DEVICE_ON_CONDITION_AUDIT.md` records all seven devices in each of
the three failed baseline corners: signed external VGS/VDS, NFET
VGS/VDS or PFET VSG/VSD, internal model VTH/VDSAT, margins, signed Id,
gm, gds, floor-gated gm/abs(Id), supply current, stage nodes, functional
metrics, and independent on/saturation/function flags. The current
floor is |Id|>1e-12 A; smaller or missing currents make gm/Id invalid,
never artificially huge. Two baseline failed corners missed only the
v2 on predicate; the FS high-VDD/cold corner also missed negative slew.
Meaningful measured current/gm in predicate-failing devices does not
turn a hard v2 failure into a pass. It argues for a separately calibrated
semantics proposal. One design cannot establish a unique cause across
the full feasible region.

## Local sensitivity and physical search attention

The 48 frozen, distinct, in-bounds proposals were measured at the five
preselected near-constraint corners. Each used 15 standard stage
analyses plus five signed-current diagnostic OP probes. All 240
candidate-corner groups succeeded. Linear/log normalized coordinates
and one-sided boundary perturbations avoided out-of-bounds duplicates.
`LOCAL_ROBUST_SENSITIVITY.csv` contains 1,680 role-corner records
with signed differences for device and performance metrics; the local
report documents the ordering and limitations. Search attention used
`tail_width_m`, `compensation_capacitance_f`, `input_pair_width_m`, `tail_length_m`; the original 12-D Benchmark-v2 bounds remained unchanged.
The two nonfailing preselected baseline Id probes were completed after
the candidate batch rather than before it; this order deviation is
disclosed and charged, without post hoc corner selection.

## Search, exact ranking and boundary concentration

The existing sequential DE implementation used seed 96001 for 64
proposals; deterministic local refinement used seed 96002 for 32.
The same frozen partial score promoted one eligible unique candidate
after each batch of 12. The 96 partial results consumed 225 analyses;
85 stopped after the first measured stage. They were never ranked as
exact. Eight promoted candidates each received a fresh Full matrix
(360 further analyses). With the fresh baseline, nine unique Full
matrices form the exact ranking.

| Exact rank | Origin | Violation | Passed corners | Failed corners |
| ---: | --- | ---: | ---: | --- |
| 1 | `promotion_07` | 1 | 12/15 | ss__high_v_low_t, fs__nominal, fs__high_v_low_t |
| 2 | `promotion_08` | 1.00663743 | 12/15 | ss__high_v_low_t, fs__nominal, fs__high_v_low_t |
| 3 | `promotion_06` | 1.01827996 | 11/15 | ss__high_v_low_t, fs__nominal, fs__low_v_high_t, fs__high_v_low_t |
| 4 | `baseline` | 1.02250476 | 12/15 | ss__high_v_low_t, fs__nominal, fs__high_v_low_t |
| 5 | `promotion_02` | 1.6149516 | 0/15 | tt__nominal, tt__low_v_high_t, tt__high_v_low_t, ss__nominal, ss__low_v_high_t, ss__high_v_low_t, ff__nominal, ff__low_v_high_t, ff__high_v_low_t, fs__nominal, fs__low_v_high_t, fs__high_v_low_t, sf__nominal, sf__low_v_high_t, sf__high_v_low_t |
| 6 | `promotion_01` | 2.00244933 | 0/15 | tt__nominal, tt__low_v_high_t, tt__high_v_low_t, ss__nominal, ss__low_v_high_t, ss__high_v_low_t, ff__nominal, ff__low_v_high_t, ff__high_v_low_t, fs__nominal, fs__low_v_high_t, fs__high_v_low_t, sf__nominal, sf__low_v_high_t, sf__high_v_low_t |
| 7 | `promotion_04` | 2.24787521 | 1/15 | tt__nominal, tt__low_v_high_t, tt__high_v_low_t, ss__nominal, ss__low_v_high_t, ss__high_v_low_t, ff__nominal, ff__low_v_high_t, ff__high_v_low_t, fs__nominal, fs__low_v_high_t, fs__high_v_low_t, sf__nominal, sf__high_v_low_t |
| 8 | `promotion_03` | 4.09150723 | 0/15 | tt__nominal, tt__low_v_high_t, tt__high_v_low_t, ss__nominal, ss__low_v_high_t, ss__high_v_low_t, ff__nominal, ff__low_v_high_t, ff__high_v_low_t, fs__nominal, fs__low_v_high_t, fs__high_v_low_t, sf__nominal, sf__low_v_high_t, sf__high_v_low_t |
| 9 | `promotion_05` | 4.58132188 | 0/15 | tt__nominal, tt__low_v_high_t, tt__high_v_low_t, ss__nominal, ss__low_v_high_t, ss__high_v_low_t, ff__nominal, ff__low_v_high_t, ff__high_v_low_t, fs__nominal, fs__low_v_high_t, fs__high_v_low_t, sf__nominal, sf__low_v_high_t, sf__high_v_low_t |

The best partial proposal was candidate 72
with 22/45 measured stages
and 23 UNKNOWN stages.
It was promoted; its independent Full result is the best exact negative
matrix (violation 1.0, 12/15). The best complete design has all hard
**performance** components zero in all 15 corners, but its operating-
region component is one in three corners. Therefore it is not a v2
witness. Top eight unique Full matrices, ranked before inspection by
exact violation, worst power and parameter hash, have 96 parameter
position rows in `BOUNDARY_CONCENTRATION.csv`. Log-sampled variables
use log normalized coordinates; near-bound counts use fixed 5% bands.
Among those eight, compensation capacitance is in the upper 5% for
five candidates and input-pair length for four; the capacitor uses
its **log-space** position. The full per-variable lower/upper counts
are in `boundary_concentration.json`. These adaptive-sample counts
are descriptive, not causal evidence.

## Witness, positive screening and neighborhood status

No promoted Full candidate passed 15/15. Thus no separate fresh
45-analysis positive witness verification, positive Hierarchical
validation, six-neighbor consistency audit or `PVT_FEASIBILITY_WITNESS.md`
was created. This follows the conditional frozen plan and leaves the
machine-readable Task 10 guard false. No fabricated positive tests
or neighborhood categories are reported.

## Provenance, proposal and limitations

PDK commit: `026824c7969ce6f4fc9678e6ca04b0a06a596c4b`; model SHA-256:
`d88fa42b4f42f7b1f6987141aa92161865cfc9ff5fbdce9bbc9f137bde3a2f61`; library SHA-256:
`17c208a699228f5acb87bf59c09c22a4c4d3937b6766b4957737d34e8e075f64`. The exact software/OS/ngspice fingerprint
is in `environment_fingerprint.json`. The 21 raw ZIPs passed
hash/size/inventory/CRC verification; individual source commits and
reproduction commands are listed in `EVIDENCE_ARCHIVE_MANIFEST.md`.
The Git-tracked compressed process ledger, candidate index and best
Full matrix are bound by `compressed_evidence_manifest.json`.
Byte-identical ZIP copies are Git-tracked under `raw_evidence/`, so a
checkout contains the raw netlists, ngspice logs and OP/waveform data.
Independent archival backup remains advisable.

`BENCHMARK_V3_PROPOSAL.md` proposes a separately approved physical
on/region-semantics calibration study, supported by nonzero Id/gm
and complete performance passes, but implements nothing. The best
candidate's signed Id was not independently probed; the baseline
Id evidence must not be transferred to it as if measured. The finite
adaptive search cannot establish global v2 infeasibility or universal
causality. Decision B therefore keeps Task 10 blocked and asks for
separate review of any versioned v3 proposal, without weakening hard
performance specs or PVT corner count.
