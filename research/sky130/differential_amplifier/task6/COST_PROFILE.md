# Task 6 Cost Profile

Accepted pilot run: cp-20260914T035056918657Z-277c0ea80877

Pre-registration commit: 05ae1f3

Candidate-design commit: 713a784

Candidate-design SHA-256:
b10e6bd63aca0d2bb1d87c46066375b73c79264c475abb9bc02869f8d7b9dd06

The fixed pilot ran 32 paired candidates and 64 real ngspice processes with
zero process failures. Sixteen pairs ran Full first and sixteen ran OP-only
first. One candidate was OP valid and 31 were OP invalid. No candidate or
measurement from this pilot is supplied to an optimizer.

| Runtime measurement | Mean | Median | Minimum | Q1 | Q3 | Maximum |
|---|---:|---:|---:|---:|---:|---:|
| OP-only outer wall time (s) | 0.567313 | 0.563000 | 0.531000 | 0.562000 | 0.578000 | 0.609000 |
| Full outer wall time (s) | 0.652437 | 0.610000 | 0.593000 | 0.609000 | 0.628750 | 1.656000 |
| Paired OP/Full wall-time ratio | 0.897582 | 0.921870 | 0.349034 | 0.896721 | 0.947541 | 0.973064 |
| OP-only ngspice process time (s) | 0.514187 | 0.516000 | - | - | - | - |
| Full ngspice process time (s) | 0.594281 | 0.562000 | - | - | - | - |

The paired Full-minus-OP outer wall-time difference has mean 0.085125 s and
median 0.047500 s. OP-only is cheaper, but process startup and device-model
loading dominate this small circuit, so it is not close to free. The isolated
Full maximum also shows why host wall-time stopping could perturb candidate
sequences.

The pre-registered decision therefore stands: logical expensive AC count is
the primary cost, while process calls and measured wall time are mandatory
secondary outcomes. The fixed 200-AC budget, 300-candidate cap, search space,
physics rules, and hypotheses are unchanged.

Published evidence:

| File | SHA-256 |
|---|---|
| pilot_raw.csv | a5b2aaa757d0831e84387871aa65299d4787ca74e43f32de6c5516b2d9ecf821 |
| pilot_summary.json | 8811d7a5ed6ba9b68ac52f61ce458861a5d317b9200ec37f955d73baec02d9b9 |
| runtime_distribution.png | 7280b23c7a1d36b3d94e87c959d214b672ad45a2fb8cb275e8957a6f443fd0ff |

