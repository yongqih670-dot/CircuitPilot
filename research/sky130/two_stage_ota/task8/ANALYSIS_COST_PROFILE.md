# Task 8 Analysis Cost Profile

Status: completed before Task 8 protocol freeze and formal experiments.

The fixed set is Task 7 formal Random seed 0, iterations 1–16. Every candidate
was re-run as OP-only, OP+AC, and Full OP+AC+transient. These measurements are
instrumentation-only and were not supplied to an optimizer.

## Identity

- Task 7 benchmark hash: 144100e168ca5f550c6ca0bd5a29788f669d0e34cd9008c5a7fe2099e8cb8c1c
- Task 7 formal evidence SHA-256: bd0670dafc8f86dee1a650ddf5a1d376a236e2285c02d022668a93f1c4163036
- new ngspice processes: 96

## Measured costs

| Mode | Metric | Median (s) | Mean (s) | Q1 (s) | Q3 (s) | IQR (s) |
|---|---|---:|---:|---:|---:|---:|
| op_only | accumulated_ngspice_seconds | 0.617000 | 0.627875 | 0.542750 | 0.641000 | 0.098250 |
| op_only | outer_wall_seconds | 0.633000 | 0.651375 | 0.558500 | 0.660000 | 0.101500 |
| op_only | orchestration_seconds | 0.023000 | 0.023500 | 0.016000 | 0.032000 | 0.016000 |
| op_ac | accumulated_ngspice_seconds | 1.140000 | 1.112188 | 0.976500 | 1.218000 | 0.241500 |
| op_ac | outer_wall_seconds | 1.172000 | 1.156500 | 1.016000 | 1.254000 | 0.238000 |
| op_ac | orchestration_seconds | 0.047000 | 0.044312 | 0.032000 | 0.048000 | 0.016000 |
| full | accumulated_ngspice_seconds | 1.733500 | 1.683625 | 1.597250 | 1.773500 | 0.176250 |
| full | outer_wall_seconds | 1.804000 | 1.749750 | 1.687000 | 1.835750 | 0.148750 |
| full | orchestration_seconds | 0.063000 | 0.066125 | 0.057500 | 0.077250 | 0.019750 |

## Check

Median accumulated subprocess time increases from OP-only (0.617000 s) to
OP+AC (1.140000 s) to Full (1.733500 s). The expected Task 7 analysis
cost ordering is therefore present in the Task 8 environment.
