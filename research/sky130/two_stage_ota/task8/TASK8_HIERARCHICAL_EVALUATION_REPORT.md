# Task 8 Hierarchical Evaluation Report

Status: complete and frozen after all pre-registered gates and formal suites passed.

## 1. Frozen Task 7 identity

Task 7 benchmark SHA-256 remained `144100e168ca5f550c6ca0bd5a29788f669d0e34cd9008c5a7fe2099e8cb8c1c`. The topology, 12-dimensional search space, PDK, measurements, hard constraints, objective, and raw Task 7 evidence were not changed.

## 2. Full policy

Full executes independent real SKY130 OP, AC, and transient analyses for every candidate and reproduces the frozen Task 7 evaluation sequence.

## 3. Hierarchical policy

Hierarchical executes OP, then AC only after all measured OP hard constraints pass, then transient only after all measured AC hard constraints pass.

## 4. Safe-rejection logic

Every early stop is caused by an already measured frozen hard-constraint violation. No prediction, learned model, heuristic parameter region, synthetic metric, or LLM judgment participates.

## 5. Replay equivalence

Offline replay covered 2000 frozen Full candidates without new ngspice calls: 1988 OP rejections, 5 AC rejections, and 7 transient-required candidates.

## 6. False rejection count

Replay false rejections: 0. Smoke shadow-Full false rejections: 0 across 300 audited hierarchical early rejections.

## 7. Partial feedback

The frozen lexicographic scalar keeps feasible candidates best, rewards later validated stages, and ranks within a stage only by measured normalized violations. Unknown downstream metrics remain null.

## 8. Analysis cost profile

On 16 fixed candidates, median accumulated simulator time was 0.617 s for OP-only, 1.140 s for OP+AC, and 1.733 s for Full. The profile used 96 new processes.

## 9. Smoke

Smoke completed 24 cells and 600 primary candidates. Stage counts were {'full_infeasible': 300, 'op_rejected': 300}; all 300 hierarchical rejections were shadow validated. Smoke is excluded from formal inference.

## 10. Equal Candidate results

Each policy evaluated 2,000 candidates (4 methods × 10 seeds × 50). Full used 6000 processes and 3750.712 accumulated ngspice seconds; Hierarchical used 2024 processes and 1479.445 seconds. Successful runs were 5/40 and 3/40, respectively.

## 11. Equal Simulation-Time results

At the frozen 90 s per-run budget and 300-candidate cap, Full evaluated 1392 candidates in 4176 processes; Hierarchical evaluated 5349 candidates in 5484 processes. Successful runs were 4/40 versus 10/40. The pre-registered implementation completes an in-flight candidate before stopping, so maximum overshoot was 2.746 s. This candidate-terminal rule is slightly broader than a literal stop immediately after the first analysis crossing the budget.

## 12. AC savings

Equal-candidate pooled paired Full-minus-Hierarchical AC savings: median 50.000, mean 49.575, bootstrap 95% CI [49.325, 49.800] analyses per run.

## 13. Transient savings

Pooled transient savings: median 50.000, mean 49.825, bootstrap 95% CI [49.650, 49.975] analyses per run.

## 14. Process-count savings

Pooled total-analysis savings: median 100.000, mean 99.400, bootstrap 95% CI [99.000, 99.725] analyses per run. Pooled process savings are numerically identical in this benchmark because every OP, AC, or transient analysis launches one ngspice process: median 100.000, mean 99.400, 95% CI [99.000, 99.725].

## 15. ngspice-time savings

Pooled accumulated-ngspice savings: median 54.043 s, mean 56.782 s, bootstrap 95% CI [53.534, 60.273] s. The median paired percentage reduction was 56.45%.

## 16. Wall-time observations

Equal-candidate summed outer wall time was 4282.009 s for Full and 1671.805 s for Hierarchical. This is secondary; accumulated subprocess time is the primary runtime metric.

## 17. KM/RMST on all cost axes

Kaplan-Meier curves and shared-horizon RMST are published for candidate, AC, transient, and accumulated-ngspice-time axes. Equal-time pooled ngspice RMST was 88.602 s for Full and 79.150 s for Hierarchical.

## 18. Stage distribution

Formal equal-candidate stage counts were {'full_infeasible': 1995, 'fully_feasible': 8, 'op_rejected': 1983, 'ac_rejected': 10, 'transient_rejected': 4}; equal-time counts were {'full_infeasible': 1388, 'fully_feasible': 27, 'op_rejected': 5261, 'ac_rejected': 41, 'transient_rejected': 24}. Per-cell counts are in `results/statistics/stage_distribution.csv`.

## 19. First blocking constraints

Across formal candidates, first blockers were {'operating_region': 10561, 'phase_margin': 54, 'output_bias': 56, 'negative_slew': 5, 'positive_slew': 26, 'ugf': 4}. The table is descriptive only and did not reorder stages.

## 20. Paired effect sizes / CI

All effects use method/seed pairing, 10,000 deterministic percentile-bootstrap resamples, and seed 82008. Per-method and pooled results plus all individual differences are published in `paired_effects.json` and `paired_differences.csv`.

## 21. Exact simulation evidence

All formal CSV records retain exact hashes, parameters, metrics, statuses, stage costs, and raw-run paths. 10 canonical best feasible raw-evidence directories are copied under `results/best_raw_evidence/`. Simulator/process failures across all primary Task 8 suites: 0.

## 22. Tests

The 24 Task 8 tests pass and cover frozen Task 7 bytes, Full equivalence, all gate transitions, null unknown metrics, feasibility identity, replay detection, cost counters, both budget types, overshoot, stage-boundary resume, deterministic feedback, fairness identity, real SKY130 E2E, paired bootstrap, and KM/RMST. The full project regression completed with 313 passed and one environment-dependent Task 3 skip because SKY130_MODEL_LIBRARY was not configured.

## 23. Limitations

Results are limited to the frozen nominal SKY130A two-stage OTA, ten seeds, four optimizers, and one machine/runtime environment. They do not cover PVT, mismatch, learned surrogates, topology generation, layout parasitics, or adaptive stage ordering. H3 is a pooled pre-registered decision and is not uniform by method: Full equal-time successes were Random 0/10, DE 1/10, TPE 3/10, BO 0/10; Hierarchical successes were Random 1/10, DE 6/10, TPE 2/10, BO 1/10. A strict 90.0 s administrative sensitivity analysis still favors Hierarchical (10/40 successes, RMST 78.553 s) over Full (3/40, RMST 87.874 s), so the candidate-terminal overshoot does not drive H3. All accepted raw run directories remain locally available, while the versioned result package contains consolidated candidate records and 10 canonical feasible raw-evidence directories rather than every raw waveform.

## 24. Hypothesis decisions

- H1: supported.
- H2: supported.
- H3: supported.
- H4: supported.

## 25. Recommendation for Task 9

Use this frozen deterministic hierarchical evaluator as the baseline. Any future agent or learned policy should preserve the same feasibility and safe-rejection audit while demonstrating paired gains beyond this baseline on simulator-time RMST and success.

## Provenance

Task 8 protocol SHA-256: `d60ad33791a59bf418b0378e653e4e3bc10aa032dc98cde583d649260844dc2d`. All suite fairness validators passed. Exact file hashes are published in `file_hashes.json`.
