# Task 7 Benchmark Difficulty Protocol

Status: frozen; this publication filename is an index over the normative
pre-registration.

The complete difficulty rule was committed before calibration in commit
c83df4b through CALIBRATION_PROTOCOL.md and DIFFICULTY_LADDER.yaml. This file
does not add or reinterpret a threshold; it records those already committed
semantics under the filename required by the Task 7 publication checklist.

## Design and target band

- Design: deterministic, unscrambled, 12-dimensional Sobol base-2 sequence.
- Size: exactly 512 points (m = 9).
- Feedback: no optimizer, ask/tell loop, adaptive stopping, or warm start.
- Evaluator: Full-only; each point attempts one OP, one open-loop AC, and one
  unity-follower transient analysis in independent real SKY130 processes.
- Target simultaneous feasible density: inclusive 0.2% through 2.0%.

The target was selected before observing calibration results so the benchmark
would be sparse enough to distinguish 50-candidate searches while still
showing empirical evidence that a feasible region exists.

## Frozen ladder and selection

The five rows in DIFFICULTY_LADDER.yaml jointly specify gain, UGF, phase
margin, power, both slew directions, output range, and all-device operating
region validity. The mechanical selection is:

1. Evaluate every row on the same complete 512-point table.
2. Among rows inside the target band, select the most stringent row.
3. If none is inside, minimize absolute log-distance to the 0.6325% geometric
   midpoint; ties select the more stringent row.
4. Freeze the selected row before any optimizer smoke or formal run.

Calibration produced row densities of 0.390625%, 0.1953125%, 0.1953125%, 0%,
and 0%. Row 1 was the most stringent row within the inclusive target band and
was therefore selected. The outcome is stored in
results/calibration/calibration_summary.json; all 512 raw rows remain in
results/calibration/calibration.csv.

## Integrity boundary

Calibration measurements were used only for the mechanical specification
selection and the pre-registered runtime budget rule. They were never given
to Random, DE, TPE, or BO. No optimizer observation changed topology, search
bounds, load, testbench, measurement semantics, or the ladder.
