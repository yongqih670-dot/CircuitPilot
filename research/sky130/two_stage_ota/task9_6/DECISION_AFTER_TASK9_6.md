# Decision after Research Task 9.6 — B

**Decision B: no Benchmark-v2 witness found within the preregistered
diagnostic budget, but measured device and performance evidence
supports a separately reviewed Benchmark-v3 proposal.** This is
not a proof that v2 is infeasible or that v3 is required.

Nine unique complete Full-PVT matrices (fresh baseline plus eight
method-blind promotions) were evaluated. None was 15/15 feasible.
The best complete result had exact robust violation 1.0 and 12/15
passing corners. It met every frozen performance hard specification
in all 15 corners; only the v2 operating-region component failed
in `ss__high_v_low_t`, `fs__nominal`, and `fs__high_v_low_t`.
The separate baseline device probe found finite Id/gm in devices
rejected by that same v2 on predicate; baseline additionally missed
negative slew in one corner. These observations justify proposing
a future measured-current/model-saturation semantics study, not
silently altering v2 or declaring the candidate feasible.

Task 10 stays blocked: no fresh positive 45-analysis verification,
positive Hierarchical validation or neighborhood audit exists, and
the machine-readable Task 10 guard remains false. Benchmark v3 is
proposal-only and needs explicit user approval in a separate task.
The exact budgeted conclusion is **no witness found within this
preregistered diagnostic budget**.
