# Fail-closed Task 10 formal-execution guard (Phase A)

The machine-readable release manifest is `task10_execution_gate.json`. Its
initial state is **blocked**. `scripts/check_task10_execution_guard.py` is a
read-only preflight; a future Task 10 formal runner must call the same
`require_task10_execution_guard()` API before candidate generation or any
formal simulator process. No Task 10 runner exists yet, and this specification
does not create one. A Markdown assertion or a Boolean-only edit cannot
unlock the guard. Phase B must issue a separately versioned release manifest
after positive evidence; the blocked Phase-A manifest remains an immutable
record of the initial state.

The approved corrected hash is code-pinned to
`8f622a92370e33ea6f608d7a31077096b8188b868dc070cebbf3ce67f9059708`.
The frozen old Task 9 hash
`ec2d4de0e0c5694598cc7444b4fa9b63a8d8b533fa68bdd504e5262ebd5e2d61`
is explicitly rejected. Changing to a future v3 requires a new reviewed
code/spec/manifest version; setting a JSON field is insufficient.

## Required release evidence

The guard must verify all of the following against actual hashed files, not
just user-set flags:

1. Manifest schema, approved corrected benchmark hash and v2 region version;
   old hash is different and never selected.
2. `verified_real_pvt_witness`, `positive_screening_validation`,
   `witness_matrix_complete`, `corner_application_checks_pass` and
   `neighborhood_consistency_audit_complete` are all true.
3. A SHA-256-locked Task 9.6 **Full** wrapper matrix has exactly the frozen
   15 corner IDs and all 45 OP/AC/transient analyses, no analysis errors,
   every hard-constraint component zero, exact robust violation zero,
   `is_feasible=true`, and every VDD/temperature application check true.
4. A separate SHA-256-locked Hierarchical wrapper for the *same parameters*
   measures a positive path without early rejection and reports feasible.
5. The locked six-candidate neighborhood audit contains Full/Hierarchical
   agreement for every deterministically generated neighbor; each referenced
   result has its own content hash. Natural infeasible/feasible mix is not
   prescribed, but every classification must agree.
6. A SHA-256-locked raw-evidence ZIP exists with all 45 witness netlists,
   logs and waveform/OP outputs; its manifest includes per-corner model
   section identity. The frozen PDK commit, model digest and library digest
   match the actual Task 7 PDK tree revalidated at preflight.
7. A SHA-256-locked environment fingerprint records the ngspice binary and
   software/OS versions. A canonical simulation-environment lock (excluding
   Git commit/worktree state, which naturally changes at Task 10) matches
   the current environment. The ngspice executable content hash is checked.
8. The manifest's `corner_count=15`, `analysis_count=45`,
   `analysis_errors=0` and all Boolean claims match recomputation from the
   evidence. Missing, invalid, unknown or path-escaping evidence fails closed.

The guard returns a machine-readable allow/deny decision with reasons and
raises on `require_task10_execution_guard()` failure. Its status is not
inferred from the existence of `PVT_FEASIBILITY_WITNESS.md`. Task 9.6 Phase A
intentionally supplies no witness or positive-validation evidence, so the
initial guard must deny Task 10. Phase B may populate evidence only after
explicit execution-plan approval and successful fresh verification; it must
not flip flags in advance. All release checks and their tests are separate
from the old Task 9 historical evaluator.
