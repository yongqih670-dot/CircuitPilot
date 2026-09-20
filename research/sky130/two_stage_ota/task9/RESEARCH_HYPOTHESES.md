# Task 9 Research Hypotheses

Status: pre-registered before nominal-gap evaluation, calibration, replay,
implementation, smoke, or optimizer experiments.

Version: `task9_pvt_hypotheses_v1`

## H1: exact feasibility preservation

Hierarchical-PVT preserves Full-PVT feasibility exactly.  H1 is supported only
if all completed-matrix offline replay candidates and all required smoke shadow
audits have zero false PVT acceptance and zero false PVT rejection.  One error
halts formal experiments; it cannot be removed by changing a corner, threshold,
stage gate, order, or candidate after observation.

## H2: equal-candidate work reduction

At an equal candidate budget, Hierarchical-PVT reduces corner starts, OP calls,
AC calls, transient calls, and total process calls.  H2 is supported only if
the pooled paired Full-minus-Hierarchical median is positive for corners, AC,
transient, and process calls, and each corresponding paired-mean 95% bootstrap
interval has a lower bound above zero.  OP savings are reported but not required
because the first corner must begin for every candidate.

## H3: equal-candidate simulator-time reduction

Analysis/corner reduction translates to accumulated ngspice-time reduction.
H3 is supported only if the pooled paired Full-minus-Hierarchical accumulated
ngspice-time mean has a 95% bootstrap lower bound above zero and the pooled
paired median percentage reduction is at least 20%.

## H4: equal-simulator-time PVT efficiency

Under one shared accumulated-ngspice-time budget and candidate cap,
Hierarchical-PVT finds robust-feasible designs more efficiently.  H4 is
supported only if it has both a strictly higher pooled run success rate and a
lower pooled accumulated-ngspice-time RMST to first PVT-feasible candidate at
the pre-specified shared-support horizon.  Candidate throughput alone cannot
support H4.

## H5: nominal-to-PVT robustness gap

The frozen nominal-feasible Task 7/8 designs are not all PVT robust.  H5 is
supported if at least one saved nominal-feasible design fails at least one
corner of the frozen 15-corner suite under ladder row 0.  This is descriptive
motivation only and cannot train a predictor, choose corners, select the ladder
row, or enter formal optimizer estimates.

## Fixed decision conventions

Formal comparisons pair Full-PVT and Hierarchical-PVT by method and seed.
Intervals use 10,000 paired percentile-bootstrap resamples with RNG seed
`92009`.  Per-method summaries use ten seed pairs; pooled 40-pair summaries are
explicitly descriptive because methods are heterogeneous.  No endpoint or
hypothesis rule changes after results are seen.

