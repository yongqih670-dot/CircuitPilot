# Task 9 Corner-Order Replay Equivalence Report

Both frozen corner orders were replayed over all 64 complete Sobol calibration
matrices.  Each replay applies the real measured row-0 hard constraints in the
fixed within-corner order OP → AC → transient and stops across corners only
after a measured hard failure.

| Result | Nominal-first | Static worst-first |
|---|---:|---:|
| Feasibility identity | 64/64 | 64/64 |
| False PVT acceptances | 0 | 0 |
| False PVT rejections | 0 | 0 |
| Corners avoided | 896 | 896 |
| OP calls avoided | 896 | 896 |
| AC calls avoided | 960 | 959 |
| Transient calls avoided | 960 | 960 |
| Process calls avoided | 2816 | 2815 |
| Simulator seconds saved | 2353.194 | 2351.176 |
| Simulator-time saving | 97.8% | 97.7% |

The integrity gate passes: both orders have 100% feasibility identity and zero
false acceptance/rejection.  The calibration set contains no Full-PVT-feasible
positive case, so positive-path safety additionally remains a mandatory unit
test and smoke shadow audit; this limitation is not hidden by the zero-error
counts.

`replay/replay_candidates.csv` retains every stopping corner/stage/constraint
and exact cost.  `replay/replay_summary.json` retains totals and the gate.
