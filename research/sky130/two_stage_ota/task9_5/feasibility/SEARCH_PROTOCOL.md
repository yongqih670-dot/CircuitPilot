# Task 9.5 diagnostic witness-search protocol

This is benchmark diagnosis, not a formal optimizer comparison. All historical
Task 9 results remain immutable. The search uses the frozen Task 7 / Task 9
12-dimensional global bounds, fixed tail bias (0.72 V), hard constraints,
15-corner suite, and additive `model_consistent_saturation_v2` semantics.

Initial deterministic run: seed 20260926; reuse only the parameters (not
cached simulation results) of the top eight immutable complete historical
matrices ranked by v2 passing corners. Evaluate each afresh at all 15 corners
with OP. Then perform up to 160 local perturbation proposals around the best
four seed/diagnostic candidates, with coordinate and coupled changes in
normalized bound coordinates, plus 40 global Sobol proposals. Each proposal
first receives OP on four stress corners (`ss__low_v_high_t`, `sf__low_v_high_t`,
`fs__low_v_high_t`, `ff__high_v_low_t`). Candidates with sufficiently good
stress-corner scores are promoted to full 15-corner OP. Any candidate with
all 15 OP constraints satisfied is promoted to fresh full 15-corner
OP/AC/transient verification. A final witness requires all 45 fresh runs,
including VDD and temperature application checks. No hard limit is changed.

The exact attempt list, parameters, evaluation mode, constraint components,
device evidence, process cost and simulation directories are recorded as an
append-only JSONL ledger and per-attempt raw files under
`research_runs/task9_5_feasibility/`. A finite run with no witness is not a
proof that the design space is empty; it triggers physical bottleneck analysis
and a Task 10 no-go until the feasibility gate is resolved.
