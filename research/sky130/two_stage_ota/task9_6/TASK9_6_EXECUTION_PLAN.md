# Task 9.6 Phase-B execution plan — frozen in Phase A, **not approved to run**

This plan is diagnostic, not an optimizer-superiority comparison. Execution
requires a new explicit user approval. Phase A stops after publishing this
plan and the other Phase-A deliverables. All runs must call the explicit
`evaluate_task9_6_benchmark_v2_candidate` boundary with frozen hash
`8f622a92370e33ea6f608d7a31077096b8188b868dc070cebbf3ce67f9059708`.
No old Task 9 v1 evaluator, hard-spec relaxation, bound expansion, v3
implementation, Task 10 Agent run, or unbudgeted SPICE probe is authorized.
Approval must be recorded as a separate Phase-B authorization; do not edit
this frozen plan's `phase_b_approved=false` field in place. If the user wants
a different budget or protocol, issue a newly versioned plan before execution.

## Fixed allocation and caps

| Activity | Candidate/evaluation cap | Worst-case ngspice processes |
| --- | ---: | ---: |
| Current-sign/model-section/device-audit probes | up to 30 charged processes | 30 |
| Fresh 15-corner Full baseline of Task 9.5 best design | 1 × 45 | 45 |
| Local sensitivity at five frozen corners | 48 candidates × (15 benchmark analyses + 5 diagnostic OP analyses) | 960 |
| Bounded witness search | 96 Hierarchical candidates × at most 45 analyses | 4,320 |
| Promotion from Hierarchical to fresh Full-PVT | at most 8 × 45 | 360 |
| Separate fresh Full witness confirmation, only if a promotion passes | at most 1 × 45 | 45 |
| Separate positive Hierarchical witness check, only after confirmation | at most 1 × 45 | 45 |
| Deterministic witness neighborhood, only after confirmation | 6 × (Full 45 + Hierarchical ≤45) | 540 |
| Failed-analysis/fresh-run retry reserve | at most 100 additional processes | 100 |
| **Total possible** | 48 sensitivity + 96 search + ≤8 promotions + conditional validation | **6,445** |

Hard ceilings, including every probe, failed process and retry:
**6,500 ngspice processes**, **6,000 accumulated simulator seconds**, and
**10 hours wall clock** from the first Phase-B process. The 55-process gap
between allocation and process ceiling is not an invitation to add
experiments: allocations above are also caps. A run stops when any ceiling
would be exceeded; no automatic budget extension or substitution occurs.
Every attempt, timeout, error, retry, call count, ngspice elapsed time and
wall time is appended to the audit ledger. If ngspice duration is missing,
use a conservatively measured process wall time and mark it estimated.
Archive raw netlists, OP/device outputs, waveforms and logs promptly after
each completed activity; record archive path, bytes, SHA-256, source commit
and reproduction command. Archive time does not create free simulator budget.

## Methods, seeds and promotion

First execute the frozen device-on audit and 48 local sensitivity candidates
exactly as `DEVICE_ON_DIAGNOSTIC_PROTOCOL.md` and
`LOCAL_SENSITIVITY_PROTOCOL.md` specify. The physically informed parameter
subset for **proposal attention only** is selected from those measurements;
all search proposals still obey the full original 12-D global bounds.
Before the first Phase-B process, implement and test the five-corner
v2-OP-plus-diagnostic-AC/transient runner and durable all-process budget
ledger described in those protocols. Approval of this plan alone does not
authorize an untested or unmetered runner.

Witness search allocates **64 DE proposals** in one deterministic run with no restart
(seed `96001`) and **32 local/trust-region proposals** anchored at the best
measured in-bounds design (seed `96002`, deterministic tie-breaking). Existing
DE/local implementations should be reused where compatible with v2 feedback.
No TPE or CMA-ES run is budgeted. Search is ordered in batches of 12
candidates. After each batch, promote at most its highest-ranked *eligible,
unique* partial candidate to fresh Full-PVT; eight batches allow at most
eight promotions. The same method-blind partial ordering in
`PARTIAL_SEARCH_SCORE.md` applies to every candidate; no optimizer identity
affects the rule. Already promoted parameter hashes cannot consume another
slot. An all-zero measured partial lower bound is **not** a success claim.

The first promoted candidate that passes a measured 15/15 Full matrix
halts additional witness-search proposals immediately. Run one independent
fresh 45-analysis Full confirmation from scratch (no partial/full cache),
then a separate Hierarchical run of the same parameters. Only both positives
permit neighborhood validation. If a promotion is invalid/error rather than
positive, it is not a witness; a budgeted retry may be attempted. Stop when
96 search candidates, eight promotions, or any global cap is exhausted.

## Fresh witness and six-neighbor validation

A witness requires all 15 frozen corners × OP/AC/transient, zero analysis
errors, verified VDD/temperature/process-model application, identical
PDK/model/environment hashes, all hard constraints passing, a complete
machine-readable matrix and raw archive. A second fresh Full matrix is
the existence proof. Hierarchical must then complete a positive path with
no false rejection. A positive synthetic unit test is not this evidence.

The deterministic neighborhood uses the confirmed witness and exactly
three frozen variables: `input_pair_length_m`,
`first_stage_load_width_m`, and `second_load_bias_v`. For each variable,
generate two distinct normalized-coordinate perturbations: `−0.01,+0.01`
when `0.02 < u < 0.98`; inward `+0.01,+0.02` at the lower 2% boundary or
`−0.01,−0.02` at the upper 2% boundary. Use log `u` for log-sampled
variables; never clip or duplicate. Run Full and Hierarchical for all six;
report the naturally observed feasible/near-boundary/infeasible mix without
forcing categories. Every Full-versus-Hierarchical feasibility classification
must agree. The machine guard remains blocked otherwise.

## Retry and stop policy

At most **one** retry of an errored ordinary stage is allowed per attempt,
charged to the 100-process retry reserve. A failed would-be witness Full
matrix is never patched with cached stages: if retry is justified, repeat
all 45 processes as a new Full run and charge the reserve. No retry is
automatic after a measured hard-constraint failure. A retry may not exceed
any activity or global cap. Stop the entire search immediately after a
confirmed positive and proceed only to positive/neighborhood validation;
stop at frozen budget exhaustion without silently extending it. If no
witness is found, report only “no witness found within the preregistered
diagnostic budget,” plus specific physical/boundary evidence. Propose v3
only if that evidence justifies it; never implement v3 or unlock Task 10
without separate approval.
