# Task 6 Cost Model

Status: pre-registered before implementation and pilot execution.

Version: task6_logical_ac_primary_cost_v1

The primary expensive cost is the count of logical AC testbench analyses:
differential_ac_calls plus common_mode_ac_calls. One combined ngspice AC
command that evaluates two isolated testbench copies therefore costs two
logical expensive analyses. Wall time is measured and reported rather than
estimated from counts.

Each candidate records candidate_evaluations, ngspice_process_calls,
dc_op_calls, differential_ac_calls, common_mode_ac_calls,
full_ac_candidate_count, expensive_ac_analysis_count, physical analysis_calls,
candidate wall-clock seconds, and cumulative wall-clock seconds.

| Policy/stage | Candidate | Processes | DC OP | Differential AC | Common AC | Full-AC candidate | Physical analyses |
|---|---:|---:|---:|---:|---:|---:|---:|
| Full | 1 | 1 | 1 | 1 | 1 | 1 | 2 |
| Screened, OP rejected | 1 | 1 | 1 | 0 | 0 | 0 | 1 |
| Screened, OP valid | 1 | 2 | 1 | 1 | 1 | 1 | 2 |

The second Screened process is necessary because CircuitPilot must parse and
classify Stage 1 before deciding whether Stage 2 is permitted. The AC process
performs the simulator's internal small-signal bias solution, but the logical
dc_op_calls field counts the explicit Stage 1 OP analysis only. Process and
logical analysis costs are never conflated.

## Pre-registered comparisons

Smoke uses both policies, four methods, seeds 0-2, and a cap of 25 candidates.

Formal Experiment A uses both policies, four methods, seeds 0-9, and exactly
100 candidates. There is no early AC-budget stop. It measures optimizer
behavior and AC work avoided at equal candidate count.

Formal Experiment B uses both policies, four methods, seeds 0-9, an expensive
AC budget of 200 logical calls, and a hard cap of 300 candidates. A run stops
before asking another candidate once either its AC budget is exhausted or its
candidate cap is reached. Since a full AC candidate consumes exactly two
logical calls, the budget cannot be overshot. Full reaches 200 calls at 100
candidates. Screened may explore OP-only candidates until it reaches 200 calls
or 300 total candidates; unused AC budget remains visible and is not imputed.

No wall-time stopping rule is used because host scheduling noise can change
candidate sequences. wall_time_policy is measured_not_stopping_v1.

