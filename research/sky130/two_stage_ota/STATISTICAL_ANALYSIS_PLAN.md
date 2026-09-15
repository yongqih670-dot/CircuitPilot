# Task 7 Statistical Analysis Plan

Status: frozen before smoke and formal optimization.

Version: task7_candidate_km_rmst_pairwise_v1

## Primary endpoint

The event is the first candidate satisfying all nine frozen hard constraints
simultaneously. Candidate count is the primary time axis. Runs without an
event by candidate 50 are right-censored at 50. Wall time and high-fidelity
analysis count are descriptive secondary axes.

For each method, report:

- event count and success rate over seeds 0--9;
- Kaplan--Meier event-free estimates on candidate count;
- restricted mean time to first feasible candidate through 50;
- median time to event only when estimable;
- final best feasible power distribution;
- all measurement-status and simulation-failure counts.

## Comparisons

All methods use paired seeds and the same frozen benchmark hash, search-space
hash, objective/constraint hash, measurement versions, ngspice settings, PDK
hashes, candidate budget, and Full evaluator identity. Pairwise method
comparisons report seed-paired RMST differences and paired success
differences. With only ten seeds, estimates are descriptive; no claim is
based solely on an uncorrected p-value.

## Integrity exclusions

Calibration rows and smoke rows cannot enter formal statistics. A formal cell
is rejected if any fairness hash differs, iterations are non-contiguous,
cost identities fail, a candidate has fewer or more than three process
attempts, or the optimizer state cannot exactly replay committed records.

