# Task 6 Execution Incident Log

## 2026-09-14 Windows parallel-runtime rejection

An initial post-smoke formal-A launch attempted four method suites concurrently
from commit a8e0d87e3ce42b423b4834fe842f7e0c62b4b527. The Windows SKY130 runtime
then selected two process-global SUBST drive aliases without atomic
reservation. Concurrent processes raced on the same letters, producing
"Drive already SUBSTed" and "not enough unused Windows drive letters" errors.

This was infrastructure failure, not circuit non-convergence. The attempt was
stopped, all four run roots were permanently deleted, and none of its rows is
accepted or used in Task 6 statistics.

The runtime was changed to execute from an isolated ASCII temporary directory
and a content-addressed ASCII cache containing the exact frozen invariant,
NFET TT, PFET TT, and their two transitive PM3 fragments. Generated netlists,
logs, and raw data are copied back to each immutable evidence directory.
Task 5 topology, model content, hashes, measurements, and objectives are
unchanged.

Verification after the fix:

- full repository regression: 237 passed, 1 environment-dependent skip;
- four simultaneous real SKY130 Task 5 integration tests: 4 passed;
- repeated frozen smoke suite:
  smoke-cp-20260914T044906766217Z-7742c608447c;
- repeated smoke totals: 24 runs, 600 candidates, 642 processes, 684 logical
  AC analyses, zero failures, and two runs reaching feasibility;
- repeated smoke fairness validation: passed;
- the repeated smoke aggregate counts exactly match the pre-fix smoke.

Wall time from concurrently scheduled formal suites is descriptive only.
Candidate count and logical differential-plus-common-mode AC count remain the
pre-registered primary axes.

## 2026-09-14 Windows CSV replacement rejection

The first formal-B launch from commit
4740ac38af261c828307dd2d463a1a14d430eb77 was stopped after Windows briefly
denied replacement of one run's evaluations.csv. SQLite had already committed
that candidate, while the optimizer checkpoint was still one row behind.
Although the physical result was intact, the existing resume path did not yet
prove that it could advance the optimizer without duplicating a candidate.

All four formal-B roots from that launch were permanently deleted and excluded.
CSV replacement now has bounded retries for transient Windows readers. Resume
also compares optimizer-history length with committed SQLite rows, regenerates
each missing candidate, requires exact parameter equality, replays its recorded
feedback, and saves the repaired checkpoint before continuing.

The added stale-checkpoint regression reproduces a database one row ahead of
the optimizer state and proves that the next candidate remains identical.
After this change the Task 6 suite has 22 passing tests, and the full repository
regression reports 238 passed with one unrelated environment-dependent skip.
