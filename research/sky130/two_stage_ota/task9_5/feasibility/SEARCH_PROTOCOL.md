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

## Pre-registered targeted continuation after initial 268 logged attempts

The initial run found a best design with 11/15 OP corners passing all OP
constraints. Four failures are narrow: input/first-load device-off margins
of 5--26 mV in SS/FS nominal or high-VDD/cold corners, and second-load
VDSAT headroom of -12 mV at SS nominal. Only the compensation capacitor is
on a bound, and that capacitor cannot affect OP. This motivates a targeted
fixed-bound local diagnostic before any search-space proposal.

Starting from that measured best parameter vector, run three deterministic
coordinate-sweep rounds over the 11 OP-relevant variables (all except the
compensation capacitor), using normalized shifts of ±0.06 and ±0.15 of each
frozen parameter range. Screen the four previously failing corners plus
SS/FS low-VDD/hot. Promote the eight lowest continuous OP-margin scores per
round to fresh 15-corner OP, plus four deterministic diversity choices. A
new champion is chosen by the number of complete OP-passing corners, then
continuous margin score. Any 15/15 OP candidate receives fresh 45-analysis
Full-PVT verification. Stop immediately if verified feasible. Log every
attempt and all raw evidence in a separate append-only run. This remains
benchmark diagnosis, not a formal optimizer comparison.
