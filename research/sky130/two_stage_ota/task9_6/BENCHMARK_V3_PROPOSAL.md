# Benchmark-v3 proposal — not adopted or implemented

The corrected Benchmark v2 stays frozen under hash `8f622a92370e33ea6f608d7a31077096b8188b868dc070cebbf3ce67f9059708`.
The old Task 9 v1 semantics must not be reinstated. This document
proposes only a separately approved research task.

## Measured physical motivation

The best Task 9.6 Full candidate satisfies gain, UGF, PM, power,
output and both slew minima at all 15 frozen corners, while the binary
v2 operating-region predicate alone rejects three corners. The fresh
baseline of the same topology fails that predicate at the same three
corners, and its rejected input/load devices carry roughly 1.6–3.0 µA
internal model Id with meaningful gm, not zero current. Model VDSAT
headroom, signed external coordinates, stage nodes and gm/abs(Id) are
recorded in `DEVICE_ON_CONDITION_AUDIT.md`. Local perturbations show
coupling among tail/input/load dimensions and the region margin.

## Proposed separate v3 investigation

Measure signed Id, gm, gm/abs(Id), model VTH/VDSAT and model saturation
for the best complete candidate at **all 15 corners** using a new
approved probe budget. Pre-register and physically calibrate a candidate
on/operating-region predicate that distinguishes a conducting, useful
amplifying device from a truly ineffective one. A possible hypothesis
is a finite, independently justified Id/gm criterion combined with
model VDSAT headroom, but no threshold or v3 hash is selected here.
Run fresh calibration and evaluate the unchanged hard performance
specifications, 15-corner set and technology legality before proposing
a versioned v3. Alternative bias/sizing-space revisions may be studied
only with separate PDK and physical justification; none is adopted.

A finite failed v2 search alone is **not** evidence of global
infeasibility. Nor do the baseline Id probes prove the best candidate
would pass any proposed v3 semantics. No v3 implementation, formal
recalibration or Task 10 execution is authorized by this proposal.
