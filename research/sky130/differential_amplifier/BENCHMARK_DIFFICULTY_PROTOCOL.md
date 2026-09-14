# Task 5 Benchmark Difficulty Protocol

Protocol version: task5_sky130_differential_difficulty_v1

Status: pre-registered before any Task 5 calibration simulation.

## Calibration population and target

Calibration uses the first 256 points of an unscrambled seven-dimensional
Sobol sequence. Seed metadata is fixed to 0, although an unscrambled sequence
does not consume randomness. Search-space decoding is identical to optimizer
decoding: logarithmic dimensions are transformed in log space and other
dimensions linearly. Optimizer feedback is forbidden.

The target frozen feasible density is 0.5%-3.0%, with a selection target of
1.5%. This is intentionally no easier than the 1%-3% Task 4 protocol while
allowing the higher-dimensional circuit to retain feasible designs.

## Specification ladder

Every row also requires output DC in [0.25, 1.55] V and all five critical
devices to pass the explicit operating-region inequalities.

| Row | Ad minimum | BW minimum | CMRR minimum | Power maximum |
|---:|---:|---:|---:|---:|
| 1 | 15 dB | 20 MHz | 35 dB | 1.0 mW |
| 2 | 18 dB | 30 MHz | 40 dB | 0.8 mW |
| 3 | 20 dB | 50 MHz | 45 dB | 0.6 mW |
| 4 | 22 dB | 75 MHz | 50 dB | 0.5 mW |
| 5 | 24 dB | 100 MHz | 55 dB | 0.4 mW |
| 6 | 26 dB | 150 MHz | 60 dB | 0.3 mW |
| 7 | 28 dB | 200 MHz | 65 dB | 0.25 mW |
| 8 | 30 dB | 300 MHz | 70 dB | 0.20 mW |

CMRR lower bounds and bandwidth lower bounds may satisfy greater-equal
constraints, but are never converted to exact values.

Selection is mechanical: retain ladder rows whose feasible density lies in
0.5%-3.0%; select the row closest to 1.5%; ties select the larger row number.
If no row is inside the band, select the row closest to 1.5% and explicitly
report that the target band was missed. Optimizer results never enter this
decision.

## Objective and budget

Feasibility is the conjunction of all hard constraints. Normalized violation
is minimized first. After feasibility, the frozen secondary objective is DC
supply power minimization.

The formal candidate budget is 100 unless calibration median candidate runtime
exceeds 1.5 seconds, in which case it is 50. This decision is made before
smoke/formal optimizer execution and cannot be changed afterward.

