# Task 7 Analysis Cost Profile

Status: descriptive publication of the frozen Full-only benchmark.

## Exact cost contract

Each candidate always attempts one OP, one open-loop AC, and one transient
analysis in three independent ngspice processes. Thus one candidate equals
three process calls and three logical high-fidelity calls. Screening is zero.
Candidate count, not wall time, is the optimizer comparison budget.

Calibration used 512 candidates and 1,536 processes. Smoke used 300
candidates and 900 processes. Formal used 2,000 candidates and 6,000
processes. Across the complete Task 7 evidence this is exactly 2,812
candidates, 8,436 processes, 2,812 OP calls, 2,812 AC calls, and 2,812
transient calls.

## Formal per-analysis runtime

All values are seconds over 2,000 formal candidates.

| Quantity | Median | Mean | Q1 | Q3 | IQR |
|---|---:|---:|---:|---:|---:|
| OP | 0.5780 | 0.57244 | 0.5310 | 0.6090 | 0.0780 |
| Open-loop AC | 0.5780 | 0.56805 | 0.5160 | 0.6090 | 0.0930 |
| Transient | 0.6090 | 0.60436 | 0.5470 | 0.6410 | 0.0940 |
| Full candidate wall time | 1.7820 | 1.74632 | 1.6090 | 1.8590 | 0.2500 |
| Orchestration/file-parse residual | 0.0000 | 0.00148 | 0.0000 | 0.0000 | 0.0000 |

The analysis timers are outer timers. Each includes launching an independent
process, loading SKY130 models, solving the requested analysis, copying
runtime files, and parsing results. The residual is candidate wall time minus
the three outer analysis timers and is clamped at zero to avoid timer
resolution noise.

## Model-free launch lower bound

A separate 30-repetition probe launches ngspice on a minimal OP netlist
without SKY130 model loading.

| Quantity | Median | Mean | Q1 | Q3 | IQR |
|---|---:|---:|---:|---:|---:|
| ngspice-reported process elapsed | 0.0320 | 0.03857 | 0.0310 | 0.0470 | 0.0160 |
| Outer launch elapsed | 0.0470 | 0.04583 | 0.0470 | 0.0470 | approximately 0 |

This probe is only a lower bound for process launch overhead. The gap between
roughly 0.03–0.05 s and the roughly 0.58–0.61 s Task 7 analysis medians
combines SKY130 model loading and solver computation. ngspice does not expose
a portable, trustworthy split between those two components, so no synthetic
allocation is reported.

Raw formal timings are in results/formal/evaluations.csv, their distribution
is in results/formal/statistics/analysis_cost_profile.json, and the launch
probe is in results/cost_profile. scripts/task7_process_overhead_probe.py
reproduces the model-free experiment.

## Task 8 implication

Task 7 establishes the no-screening reference. A future Task 8 should measure
whether early rejection reduces end-to-end candidate wall time under this
same high-cost topology. It must compare exact saved analysis counts and
outer wall time; it must not assume that fewer analyses automatically imply a
wall-clock improvement.
