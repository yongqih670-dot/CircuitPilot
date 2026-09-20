# Task 9 Frozen PVT OTA Benchmark

Status: frozen after capability audit, preregistration, nominal-gap evaluation,
Sobol64 Full-PVT calibration, mechanical specification selection, static-order
derivation, and replay equivalence; before formal evaluator implementation.

Version: `task9_pvt_ota_benchmark_v1`

## Ancestry

- Task 7 benchmark: `144100e168ca5f550c6ca0bd5a29788f669d0e34cd9008c5a7fe2099e8cb8c1c`
- Task 8 protocol: `d60ad33791a59bf418b0378e653e4e3bc10aa032dc98cde583d649260844dc2d`
- Frozen Task 7 YAML bytes: `077a42c053dfa59b6deb6e19dbca6cd74bec8122ebcb17998b906a4aa590df28`
- Task 7 search space: `36e72bd54d2b1850af1ce1c8a69dbe7de22f552d49713edfbb0d3de83cd4f6db`
- SKY130 model tree: `d88fa42b4f42f7b1f6987141aa92161865cfc9ff5fbdce9bbc9f137bde3a2f61`
- Open_PDKs top library: `17c208a699228f5acb87bf59c09c22a4c4d3937b6766b4957737d34e8e075f64`

The Task 7 topology, role mapping, twelve-dimensional search space, device
models, ideal load/compensation components, nominal testbench waveforms,
frequency grid, measurement semantics, and operating-region rules are
unchanged.  Task 7/8 raw results and hashes are never edited.

## Robustness suite

The benchmark crosses real TT, SS, FF, FS, and SF NFET/PFET primitive fragments
with (1.80 V, 27 C), (1.62 V, 125 C), and (1.98 V, -40 C), producing 15 frozen
corners.  `PVT_CORNER_PROTOCOL.md` is normative.  Mismatch, Monte Carlo,
parasitics, topology generation, surrogate prediction, learned corner models,
and adaptive ordering are out of scope.

Corner-suite SHA-256 and the final PVT benchmark SHA-256 are recorded in
`task9_protocol_manifest.json` and `task9_pvt_ota_frozen.yaml`.

## Frozen hard specification

Mechanical ladder selection chose row 0, identical to Task 7:

- gain >= 12 dB;
- UGF >= 0.5 MHz with the frozen valid-status semantics;
- phase margin >= 35 degrees with a measured selected crossing;
- DC power <= 1.5 mW;
- positive and negative slew >= 0.5 MV/s;
- output DC in [0.10 V, 1.70 V]; and
- all seven devices operating-region valid.

All required measurements/statuses must be valid.  PVT feasibility is the
logical AND of the complete hard specification over all 15 corners.  No metric
is averaged to establish feasibility.

Calibration found 0/64 robust-feasible candidates at every preregistered
ladder row, so the target 0.1%--2.0% density was not achieved; the frozen
same-distance/stricter-row fallback selected row 0.  This is an explicit
benchmark-difficulty limitation, not grounds to remove corners or weaken the
operating-region requirement.

## Objective

For every constraint, compute normalized violation at each corner and then take
the maximum over corners.  Sum the per-constraint maxima.  Only zero robust
violation plus valid measurements at every corner is feasible.  Among feasible
candidates minimize worst-corner DC power.  Different metrics retain their own
worst-corner identity; the benchmark defines no universal worst corner.

## Orders and experiment design

- Full-PVT: canonical suite order, but always evaluates every corner.
- Hierarchical-PVT: static worst-first order from independent Sobol64
  calibration, hash-bound and identical for every candidate.
- Nominal-first: replay/descriptive comparison only.
- Optimizers: Random, DE, TPE, BO with their frozen Task 8 configurations.
- Smoke seeds 0,1,2; 10 candidates per cell.
- Formal paired seeds 0--9.
- Equal-candidate budget: 20 per cell.
- Equal-time budget: 375.41500000166707 accumulated ngspice seconds per cell.
- Equal-time candidate cap: 100; check budget only after a completed analysis.

Capability, gap, calibration, order, replay, hypothesis, and statistical files
are evidence or protocol inputs, not optimizer training data.

