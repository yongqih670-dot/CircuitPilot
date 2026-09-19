# Task 8 Offline Replay Equivalence Report

Status: PASS

This audit replayed the frozen Task 8 staged rules over all
2000 saved Task 7 Full candidates. It launched zero
new ngspice processes and is not counted as a Task 8 simulation experiment.

## Identity

- Task 7 benchmark hash: 144100e168ca5f550c6ca0bd5a29788f669d0e34cd9008c5a7fe2099e8cb8c1c
- Task 7 formal evidence SHA-256: bd0670dafc8f86dee1a650ddf5a1d376a236e2285c02d022668a93f1c4163036
- Task 8 hierarchical policy hash: ff9f9e0301143bdb6b82974911e6dae1e35490ef209e326c8f1453d8558c757d
- evaluation-stage semantics hash: c32c752c254f4d5aac457b4be6e4eab019885ea6789a8e329b21f758025305b7

## Replay outcomes

| Outcome | Count |
|---|---:|
| OP rejected | 1988 |
| AC rejected | 5 |
| Transient rejected | 2 |
| Fully feasible | 5 |
| Transient required | 7 |
| Task 7 Full feasible | 5 |
| False rejection | 0 |

## First blocking constraints

| Constraint | Count |
|---|---:|
| negative_slew | 1 |
| operating_region | 1976 |
| output_bias | 12 |
| phase_margin | 5 |
| positive_slew | 1 |

## Gate decision

The required criterion is false_rejection_count == 0. The observed count is
0; therefore the replay gate
passes and Task 8 may proceed to cost profiling.
