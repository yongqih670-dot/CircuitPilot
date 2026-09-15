# SKY130 Two-Stage Miller OTA Benchmark

Status: frozen after calibration and before optimizer execution.

## Identity

| Item | Frozen value |
|---|---|
| Benchmark SHA-256 | 144100e168ca5f550c6ca0bd5a29788f669d0e34cd9008c5a7fe2099e8cb8c1c |
| Search-space SHA-256 | 36e72bd54d2b1850af1ce1c8a69dbe7de22f552d49713edfbb0d3de83cd4f6db |
| Protocol-family SHA-256 | 3c8cb79cb7ca41cd064ce52c68630dda40f43dd48b2b5c97a902d3553bc980c9 |
| PDK model-tree SHA-256 | d88fa42b4f42f7b1f6987141aa92161865cfc9ff5fbdce9bbc9f137bde3a2f61 |
| Model-library SHA-256 | 17c208a699228f5acb87bf59c09c22a4c4d3937b6766b4957737d34e8e075f64 |

The executable frozen configuration is two_stage_ota_frozen.yaml. Any change
to its topology, role mapping, model, search space, measurements, constraints,
objective, or cost contract requires a new version, hash, calibration, and
formal experiment.

## Circuit

The benchmark is a seven-device, single-ended, two-stage
Miller-compensated OTA:

- M1/M2: matched NMOS differential pair.
- M3/M4: matched PMOS current-mirror active load.
- M5: NMOS tail current source.
- M6: NMOS common-source second stage.
- M7: PMOS second-stage current-source load.
- Cc: Miller capacitor from stage1_out to vout.
- CL: fixed 1.0 pF capacitor from vout to ground.

Every sky130_fd_pr__nfet_01v8 and sky130_fd_pr__pfet_01v8 instance explicitly
connects drain, gate, source, and bulk. The benchmark uses SKY130A/Open_PDKs
1.0.606, TT, 27 C, VDD = 1.8 V, input common mode = 0.9 V, and tail gate bias
= 0.72 V. The M7 gate bias is one design variable. The exact connectivity is
in TOPOLOGY_PROTOCOL.md.

## Twelve role-matched variables

M1/M2 share input-pair W/L, M3/M4 share first-stage-load W/L, and M5, M6, and
M7 each have role-level W/L. The remaining variables are M7 bias voltage and
Cc. This yields 12 dimensions without artificial per-device mismatch.
Widths and Cc use logarithmic sampling; lengths and bias use linear sampling.
SEARCH_SPACE_RATIONALE.md contains every bound, unit, and expected influence.

## Full evaluation and measurements

Every candidate attempts exactly three independent ngspice processes:

1. Balanced-input OP records supply current, power, stage voltages, and
   VGS/VDS/VTH/gm/gds/VDSAT for all seven devices.
2. Unit-differential open-loop AC records gain, optional -3 dB bandwidth,
   UGF status/value or lower bound, crossing count, and interpolated phase
   margin.
3. Unity-follower transient applies the frozen 0.8 V to 1.0 V and back step
   and records fixed-window, interpolated positive and negative 20–80% slew.

The stored field ugf_hz is the benchmark's unity_gain_frequency_hz metric.
The stored positive_slew_v_per_s and negative_slew_v_per_s fields are the
positive_slew_rate and magnitude of negative_slew_rate, respectively.
MEASUREMENT_SEMANTICS.md is normative.

## Feasibility and objective

All constraints must hold simultaneously: gain at least 12 dB, UGF at least
0.5 MHz, phase margin at least 35 degrees, power at most 1.5 mW, both slew
magnitudes at least 0.5 MV/s, output from 0.10 V through 1.70 V, and all seven
devices valid under the explicit operating-region rules.

The scalar objective is lexicographic and feasibility-first. It minimizes
normalized hard-constraint violation for infeasible candidates. Only among
feasible candidates does it minimize DC power. A low scalar power cannot
override infeasibility.

## Published evidence

The results directory contains the full 512-point calibration, 12-cell smoke
suite, 40-cell formal suite, per-candidate evaluations, status taxonomy,
survival statistics, detailed distributions, best-feasible raw ngspice
evidence, cost profiles, fairness hashes, and a SHA-256 file index. Task 7 has
no screening, hierarchy, multi-fidelity path, or adaptive search space.
