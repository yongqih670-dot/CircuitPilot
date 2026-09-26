# Decision gate for Task 10

## Decision C — benchmark not yet proven solvable

**Do not start Task 10 formal Agent experiments or make optimizer-superiority
claims.** The required real 15-corner PVT-feasible witness was not found in
the unchanged Task 9 global bounds. The strongest fresh in-bounds diagnostic
design passed 12/15 corners in a complete 45-analysis matrix, not 15/15.
Consequently no real positive-path hierarchical screening validation or
boundary-validation set can yet be claimed.

The other audits impose a separate, non-negotiable identity condition for
any future restart: v2 operating-region semantics materially change nominal
hard feasibility and static safe-rejection points. The old Task 9 PVT
benchmark hash `ec2d4de0e0c5694598cc7444b4fa9b63a8d8b533fa68bdd504e5262ebd5e2d61`
must **not** be used for a corrected-semantic Task 10. The additive
semantics-only Benchmark v2 hash is
`8f622a92370e33ea6f608d7a31077096b8188b868dc070cebbf3ce67f9059708`.
It preserves the old search bounds and hard specifications but is not yet
licensed for formal Agent comparison because its feasible region lacks a
verified positive design. If a justified redesign changes the search space
or specs, assign another new hash before using it.

Decision A fails both the unchanged-feasibility and witness requirements.
Although the region-semantics change independently satisfies the rationale
for Decision B (a new hash), choosing B alone would obscure the stronger
unresolved existence gate. This document therefore selects exactly one
operational outcome: **C**, with v2 identity mandatory if feasibility work
continues. Multiple-crossing analysis found no reason to change PM semantics.

To clear C: pre-register further physically informed feasibility diagnosis
without weakening hard constraints; find a real in-bounds or separately
versioned, justified-space candidate; rerun fresh 15 × OP/AC/transient with
model/PDK/environment evidence; then verify the real positive under
Hierarchical-PVT and a small deterministic boundary set. Only after that
may Task 10 formal research begin.
