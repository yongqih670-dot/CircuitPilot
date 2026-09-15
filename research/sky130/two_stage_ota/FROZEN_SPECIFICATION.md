# Task 7 Frozen Specification

Status: frozen after calibration and before optimizer smoke/formal runs.

Calibration selected ladder row 1 mechanically: 2 of 512 Sobol candidates
were simultaneously feasible (0.390625%), within the pre-registered
0.2%--2.0% interval. The frozen hard constraints are:

| Constraint | Threshold |
|---|---:|
| DC gain | at least 12 dB |
| UGF | at least 0.5 MHz |
| Phase margin | at least 35 degrees |
| DC power | at most 1.5 mW |
| Positive slew magnitude | at least 0.5 MV/s |
| Negative slew magnitude | at least 0.5 MV/s |
| Output DC voltage | 0.10 V through 1.70 V |
| Device operating regions | all seven valid |

All constraints must hold simultaneously. Feasibility dominates every
infeasible result. Among feasible designs only, lower DC power is preferred.
No gain, UGF, phase margin, or slew trade-off can compensate a violated hard
constraint.

The resolved benchmark SHA-256 is
144100e168ca5f550c6ca0bd5a29788f669d0e34cd9008c5a7fe2099e8cb8c1c.
The search-space SHA-256 is
36e72bd54d2b1850af1ce1c8a69dbe7de22f552d49713edfbb0d3de83cd4f6db.
The PDK model-tree SHA-256 is
d88fa42b4f42f7b1f6987141aa92161865cfc9ff5fbdce9bbc9f137bde3a2f61,
and the top-level model-library SHA-256 is
17c208a699228f5acb87bf59c09c22a4c4d3937b6766b4957737d34e8e075f64.

Formal design: Random, DE, TPE, and BO; seeds 0--9; 50 Full candidates per
cell. Smoke design: the same four methods; seeds 0--2; 25 Full candidates per
cell. Any semantic change requires a new version, new hash, new calibration,
and complete restart.
