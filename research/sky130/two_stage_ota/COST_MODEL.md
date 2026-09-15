# Task 7 Cost Model and Budget

Status: frozen after calibration and before smoke/formal optimization.

Version: task7_full_three_independent_processes_v1

The primary budget is candidate evaluations. Every candidate has exactly one
OP call, one open-loop differential AC call, one unity-follower transient
call, three independent ngspice processes, and three high-fidelity logical
analysis calls. There is no screening, early rejection, multi-fidelity level,
or Task 6 policy branch.

Every candidate record stores:

- candidate, process, OP, AC, transient, and high-fidelity counts;
- OP, AC, transient, and total candidate wall-clock seconds;
- cumulative versions of every count and wall time.

The complete calibration medians were 0.625 s for OP, 0.610 s for AC,
0.656 s for transient, and 1.890 s per candidate. The mechanical budget rule
is 100 candidates when median Full candidate time is at most 1.0 s and 50
candidates otherwise. Therefore the formal budget is 50 candidates per
method/seed. Smoke uses 25 candidates per method for seeds 0--2.

Separate per-analysis cost profiles are reported from the candidate records;
they are descriptive and never alter a candidate sequence or budget.

