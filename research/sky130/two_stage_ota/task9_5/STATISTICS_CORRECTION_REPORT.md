# Task 9.5 Survival and RMST Correction

## Rule and evidence

For every method/policy comparison, the correction uses the minimum of the
largest *observed* event or censoring times in the compared groups.  KM is
administratively censored at that common horizon.  The corrected estimator
rejects a requested horizon beyond its group's observed support.  This avoids
integrating a positive survival tail after the last participant left the risk
set.  A zero survival tail after all events is still truncated conservatively.

`statistics/corrected_rmst.csv` contains all 420 recalculated group/axis rows,
including old and corrected RMST, both horizons, event counts, and change.
`statistics/corrected_km_curves.csv` contains the corresponding recomputed KM
coordinates.  `scripts/task9_5_audit_statistics.py` reads the frozen Task 6
run summaries, Task 7 candidate records, and Task 8/9 cell summaries; it writes
only this Task 9.5 correction package.  The historical result files and hashes
are unchanged.

The audit covers candidate count and recorded analysis count axes for Tasks
6--9.  Task 7--9 simulator-time axes were recomputed from saved analysis
runtimes or accumulated ngspice seconds.  Task 6 saved candidate wall time and
AC call counts, but not per-analysis ngspice elapsed seconds in its frozen
evaluation records.  A Task 6 simulator-time RMST cannot be reconstructed
without inventing a cost, so none is reported.  Wall time is not substituted.

## Corrections

| Historical comparison | Old horizon / RMST | Supported horizon / corrected RMST | Consequence |
|---|---|---|---|
| Task 6 formal equal-AC, BO Full, candidate count | 300 / 169.000 | 100 / 69.000 | Old Full tail included 200 unobserved candidates. |
| Task 6 formal equal-AC, BO OP-screened, candidate count | 300 / 151.000 | 100 / 83.400 | Shared follow-up is 100 candidates. |
| Task 6 formal equal-AC, BO Full, expensive AC | 200 / 138.000 | 84 / 74.000 | The method pair supports 84 AC calls. |
| Task 6 formal equal-AC, BO OP-screened, expensive AC | 200 / 49.000 | 84 / 37.400 | The method pair supports 84 AC calls. |
| Task 6 formal equal-AC, pooled Full, expensive AC | 200 / 119.850 | 92 / 76.100 | Pooled Full has a shorter supported AC horizon. |
| Task 6 formal equal-AC, pooled OP-screened, expensive AC | 200 / 34.742 | 92 / 34.742 | No change: its survival curve reached zero before 92. |
| Task 8 formal equal-candidate, Random Full and Hierarchical, ngspice seconds | 48.012 / 48.012 each | 30.718 / 30.718 each | Old horizon came from other methods and exceeded this method pair's support. |
| Task 8 formal equal-time, pooled Full, ngspice seconds | 90.797 / 88.602 | 90.797 / 88.602 | Unchanged. |
| Task 8 formal equal-time, pooled Hierarchical, ngspice seconds | 90.797 / 79.150 | 90.797 / 79.150 | Unchanged. |
| Task 9 formal equal-time, pooled Full and Hierarchical, ngspice seconds | 113.471 / 113.471 each | 113.471 / 113.471 each | Unchanged; all runs are censored with no feasible event. |

Across 420 recalculated rows, 48 historical RMST values changed: 28 Task 6
and 20 Task 8. Task 7 and Task 9 historical RMST values did not change. Task
6's legacy code used candidate cap or AC budget as the horizon even when the
compared group stopped earlier. Task 8 used one design-wide horizon for all
methods, exceeding support in some individual method pairs. Task 7's formal
candidate budget was fully observed. Task 9 already selected a common horizon
within each method pair. The Task 9 bootstrap code can use a fixed original
horizon in resamples whose sampled maximum is shorter; its reported primary
effect remains exactly zero because all 80 equal-time runs have no events.
Future bootstrap implementations should verify support for each resample.

## Hypothesis and conclusion impact

- Task 6 H2 remains supported on its preregistered pooled expensive-AC
  comparison: OP-screened had 37/40 successes against Full's 28/40 and corrected
  AC RMST 34.742 against 76.100.  The historical 119.850 Full RMST must not be
  cited as a supported equal-horizon estimate.  Individual method RMST values
  in the old report require the corrected table when quoted.
- Task 7 formal candidate-time conclusions remain numerically unchanged.
  New Task 9.5 analysis/process/runtime axes are descriptive additions.
- Task 8 H3 remains supported on its preregistered pooled equal-time endpoint:
  Full had 4/40 successes and RMST 88.602 seconds; Hierarchical had 10/40 and
  RMST 79.150 seconds at the common 90.797-second horizon.  Some method-level
  and equal-candidate RMST descriptions change and must use the corrected table.
- Task 9 H4 remains unsupported: both policies had 0/40 PVT successes and the
  corrected pooled RMST difference is 0 at 113.471 seconds.  No Task 9
  feasibility or cost saving conclusion changes from this statistics audit.

These are addenda to historical inference, not amendments to the frozen
datasets or benchmark identities.  Regression tests cover common horizon,
unsupported tail rejection, zero-cost censoring, and administrative censoring.
