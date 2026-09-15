# Research Task 7: SKY130 Two-Stage Miller OTA

## Executive result

Task 7 establishes CircuitPilot's third immutable transistor-level SKY130
benchmark and its first deliberately high-cost OTA sizing baseline. The
benchmark is a real seven-MOS, two-stage Miller-compensated OTA with a
12-dimensional role-matched search space. Every candidate receives OP,
open-loop AC, and unity-follower transient analyses in three independent
ngspice processes; there is no screening.

The 512-point non-adaptive Sobol calibration found 2 simultaneously feasible
points under the mechanically selected ladder row, a density of 0.390625%
inside the pre-registered 0.2%–2.0% band. Calibration median Full-candidate
runtime was 1.890 s, so the frozen budget rule selected 50 candidates per
formal cell.

The formal experiment completed all 40 method/seed cells and all 2,000
candidates without a simulation failure. TPE found a feasible design in
3/10 runs, DE in 2/10, and Random and BO in 0/10. At this small ten-seed
sample, these are descriptive baseline results, not claims of universal
algorithm superiority.

## Research freeze and execution order

Tasks 5 and 6 remained byte-identical. Their frozen identities are checked by
tests and recorded in PRIOR_RESEARCH_FREEZE_AUDIT.md. In particular:

- Task 5 benchmark SHA-256:
  57d2183621ecf37e5ca22e012452c43fce6459be7d347a5cfc93d0b394c14378.
- Task 6 policy-family SHA-256:
  53b1eb73160b4d069135f406613cd1249fcdd002bfd6cb2b0c8892da1c3b4867.

The Task 7 chronology is auditable in Git: topology and search prior were
pre-registered in ae71a46; measurement and calibration semantics were frozen
in c83df4b; calibration evidence and the selected specification were frozen
in 4c77cb2; and the Full-only experiment runner was committed in aa9f59d.
The formal suite ran from clean commit
aa9f59da0fdeca4aeff2b4261dc4534df064b29a.

## Topology and device-role mapping

The selected canonical topology contains:

| Devices | Function | Shared design role |
|---|---|---|
| M1, M2 NMOS | Differential input pair | input_pair W/L |
| M3, M4 PMOS | Current-mirror active load | first_stage_load W/L |
| M5 NMOS | Tail current source | tail_source W/L |
| M6 NMOS | Common-source second stage | second_stage_device W/L |
| M7 PMOS | Second-stage current-source load | second_stage_load W/L |
| Cc | stage1_out-to-vout Miller compensation | compensation capacitance |
| CL | vout-to-ground load | fixed 1.0 pF |

All MOS drain, gate, source, and bulk terminals are explicit. M1/M2 and M3/M4
are role matched; no implicit bulk, fake model, or fallback N1 model exists.
The tail gate is fixed at 0.72 V. M7 has an explicit gate-bias design
variable. TOPOLOGY_PROTOCOL.md is the normative connection table.

## PDK provenance and fixed conditions

The devices are sky130_fd_pr__nfet_01v8 and
sky130_fd_pr__pfet_01v8 from SKY130A/Open_PDKs 1.0.606, PDK commit
026824c7969ce6f4fc9678e6ca04b0a06a596c4b and primitive commit
403964dc7f9cca5ec1a8cc7b4f2a6f532b781676. The model-tree SHA-256 is
d88fa42b4f42f7b1f6987141aa92161865cfc9ff5fbdce9bbc9f137bde3a2f61;
the top-level model-library SHA-256 is
17c208a699228f5acb87bf59c09c22a4c4d3937b6766b4957737d34e8e075f64.

All runs use TT, 27 C, VDD = 1.8 V, input common mode = 0.9 V, tail bias =
0.72 V, and CL = 1.0 pF.

## Search dimensions and prior

The 12 variables are W/L for each of five matched roles, M7 gate bias, and Cc.
Widths span 0.42 or 0.84 micrometres through 30–60 micrometres depending on
role. Lengths span 0.15 micrometres through 1.0 or 1.2 micrometres. M7 bias
spans 0.25–1.20 V, and Cc spans 0.05–5.0 pF. Widths and Cc are sampled
logarithmically; lengths and bias are sampled linearly. The full table and
the pre-result circuit rationale are in SEARCH_SPACE_RATIONALE.md.

The search-space SHA-256 is
36e72bd54d2b1850af1ce1c8a69dbe7de22f552d49713edfbb0d3de83cd4f6db.
No Task 6 data or Task 7 optimizer observation set these bounds.

## DC, AC, UGF, phase-margin, and slew semantics

The balanced-input OP analysis records supply current, power, stage1_out,
vout, and VGS/VDS/VTH/gm/gds/VDSAT for all seven devices. NMOS validity is
VGS greater than VTH and VDS at least VGS minus VTH. PMOS uses the
corresponding absolute VSG/VSD inequalities. All seven devices must be valid.

The open-loop AC testbench applies +0.5 and -0.5 phasors to produce a unit
differential input. Parsed frequency must be positive and increasing; gain
and phase must be finite. Phase is explicitly converted from radians to
degrees in the netlist and then unwrapped. UGF is the first descending 0 dB
crossing, interpolated in gain against log-frequency. All descending
crossings are counted. Phase margin uses the phase interpolated at that same
crossing, not the nearest bin.

UGF distinguishes measured, right_censored, no_crossing, invalid_response,
and analysis_error. A response above 0 dB at f_stop stores only a lower bound.
Phase margin is unavailable without a valid selected crossing.

The transient testbench is a unity follower commanded from 0.8 V to 1.0 V at
0.5 microseconds and back at 2.0 microseconds. It stops at 4.0 microseconds
with a 2 ns maximum step. Positive and negative slew are fixed 20–80%
crossing slopes after a 5 ns edge-exclusion interval; they never use an
arbitrary maximum numerical derivative. Halving the maximum step to 1 ns
changed positive slew by 0.067% and negative slew by 1.45%, below the
pre-freeze 5% tolerance.

MEASUREMENT_SEMANTICS.md contains the exact versioned rules.

## Frozen specification and objective

Calibration mechanically selected ladder row 1:

| Hard constraint | Frozen threshold |
|---|---:|
| DC gain | at least 12 dB |
| UGF | at least 0.5 MHz |
| Phase margin | at least 35 degrees |
| DC power | at most 1.5 mW |
| Positive slew magnitude | at least 0.5 MV/s |
| Negative slew magnitude | at least 0.5 MV/s |
| Output DC voltage | 0.10–1.70 V inclusive |
| Operating region | all seven devices valid |

All constraints must hold for is_feasible to be true. The objective is
lexicographic: minimize normalized total hard-constraint violation first;
only feasible designs compete on lower DC power.

The frozen benchmark SHA-256 is
144100e168ca5f550c6ca0bd5a29788f669d0e34cd9008c5a7fe2099e8cb8c1c.
The protocol-family SHA-256 is
3c8cb79cb7ca41cd064ce52c68630dda40f43dd48b2b5c97a902d3553bc980c9.
The executable publication filename is two_stage_ota_frozen.yaml.

## Calibration

Calibration used exactly 512 deterministic unscrambled Sobol points with no
optimizer feedback. All 512 candidates completed, producing 512 OP, 512 AC,
512 transient, and 1,536 process calls with zero analysis errors.

| Quantity | Result |
|---|---:|
| Simultaneously feasible | 2 / 512 |
| Feasible density | 0.390625% |
| UGF measured / no crossing | 299 / 213 |
| Phase margin measured / unavailable | 299 / 213 |
| Positive slew measured / insufficient | 286 / 226 |
| Negative slew measured / insufficient | 269 / 243 |
| OP valid / invalid | 9 / 503 |
| UGF right-censored | 0 |
| Simulation errors | 0 |

The observed density is in the frozen target band. CALIBRATION_PROTOCOL.md,
BENCHMARK_DIFFICULTY_PROTOCOL.md, DIFFICULTY_LADDER.yaml, and the raw
calibration table provide the complete audit trail.

## Smoke validation

Smoke ran Random, DE, TPE, and BO for seeds 0–2 and 25 candidates per cell.
All 12 cells completed under one Full evaluator and identical hashes. This is
300 candidates, 900 processes, and 300 calls of each analysis; screening
calls were zero. No smoke run found a feasible design, so every method had
success rate 0, no estimable KM median, and candidate RMST 25. Smoke is a
pipeline, evidence, checkpoint, and fairness validation only.

## Formal traditional baseline

Formal ran the four methods for seeds 0–9 with 50 candidates per cell. All
40 cells and 2,000 candidates completed. Fairness validation passed, with
6,000 process/high-fidelity calls, 2,000 OP calls, 2,000 AC calls, 2,000
transient calls, and zero screening calls.

| Method | Successful runs | Success rate | KM median | Candidate RMST | Median best objective | Median best violation | Best feasible power |
|---|---:|---:|---:|---:|---:|---:|---:|
| Random | 0/10 | 0% | not estimable | 50.0 | 2.0000 | 1.0000 | none |
| DE | 2/10 | 20% | not estimable | 46.8 | 1.7198 | 0.7198 | median 134.23 uW; min 69.68 uW |
| TPE | 3/10 | 30% | not estimable | 43.5 | 2.0000 | 1.0000 | median 79.05 uW; min 51.86 uW |
| BO | 0/10 | 0% | not estimable | 50.0 | 2.0000 | 1.0000 | none |

Median best objective and violation are across all ten runs, including
censored runs without a feasible result. This explains why TPE can have more
successful runs while its across-run median remains infeasible.

The seed-paired restricted-time differences, left minus right, were
Random–DE +3.2, Random–TPE +6.5, Random–BO 0, DE–TPE +3.3, DE–BO -3.2, and
TPE–BO -6.5 candidates. They are descriptive at n = 10.

## Core metric distributions

The following are per-method medians over all formal candidates for DC gain,
power, and output voltage. UGF, phase margin, and slew medians are conditional
on that measurement having a numeric value; missing/no-crossing/insufficient
statuses remain explicit and are not imputed.

| Method | Gain dB | UGF MHz | PM deg | Power uW | Output V | Positive slew MV/s | Negative slew MV/s |
|---|---:|---:|---:|---:|---:|---:|---:|
| Random | 9.245 | 5.585 | 78.24 | 41.87 | 0.0275 | 2.975 | 7.810 |
| DE | 20.690 | 2.128 | 86.26 | 49.18 | 0.1993 | 2.150 | 3.189 |
| TPE | 28.072 | 2.564 | 81.54 | 38.41 | 1.1796 | 3.014 | 3.531 |
| BO | 4.795 | 2.454 | 86.17 | 53.36 | 0.0808 | 2.759 | 3.926 |

Full min/Q1/median/mean/Q3/max distributions are stored in
results/formal/detailed_statistics.json.

## Status distributions

Simulation failure, measurement failure, physical infeasibility, and
specification failure remain distinct. The published status_taxonomy.csv is
a deterministic post-processing sidecar from frozen candidate fields; it did
not feed any optimizer.

| Method | OP invalid | No valid UGF | PM insufficient | Slew insufficient | AC invalid | Transient failure | Simulation failed |
|---|---:|---:|---:|---:|---:|---:|---:|
| Random | 98.4% | 42.4% | 18.8% | 50.2% | 0% | 0% | 0% |
| DE | 98.6% | 24.0% | 11.8% | 36.6% | 0% | 0% | 0% |
| TPE | 98.8% | 17.0% | 10.0% | 26.4% | 0% | 0% | 0% |
| BO | 99.4% | 44.6% | 13.2% | 56.4% | 0% | 0% | 0% |

Across 2,000 candidates, stability classification counted 1,091 stable
responses, 269 responses with insufficient phase margin, and 640 with no
valid unity crossing. There were no invalid AC parses, right-censored UGF
measurements, transient analysis errors, DC non-convergence events, or
process failures. An insufficient slew transition is a measurement/spec
outcome, not a transient process failure; an invalid device region is a
physical infeasibility, not an ngspice failure.

## Cost profile

Formal medians were 0.578 s for OP, 0.578 s for AC, 0.609 s for transient,
and 1.782 s per Full candidate. Means were 0.572, 0.568, 0.604, and 1.746 s;
IQRs were 0.078, 0.093, 0.094, and 0.250 s, respectively.

A 30-launch model-free ngspice probe measured a process-elapsed median of
0.032 s and outer-launch median of 0.047 s. It is a lower bound only. The
remaining gap combines SKY130 model loading and solver computation, which
cannot be separated trustworthily with current portable ngspice telemetry.
ANALYSIS_COST_PROFILE.md reports the complete distributions and caveat.

## Fairness and reproducibility

Every method/seed cell has the same benchmark, search-space, protocol-family,
topology, role-mapping, PDK, model-library, UGF, phase-margin, transient,
slew, load/testbench, cost-model, and objective identities. A difference in
cell coverage, budget, any binding hash, or the exact 1:3:1:1:1 cost identity
raises FairComparisonError.

Raw candidate evidence is stored in CSV and SQLite at run time. Publication
includes combined CSVs, suite states, statistics, per-candidate status
taxonomy, best-feasible raw netlists/data/logs, and results/file_hashes.json.

## Tests

Fifty Task 7 tests pass. They cover topology, explicit bulks, role matching,
Miller mapping, OP/power parsing, AC gain, interpolated and censored UGF,
phase unwrap/interpolation, multiple crossings, stability classification,
transient construction, positive/negative slew, invalid semantics, operating
regions, exact cost accounting, hash sensitivity, Task 5/6 byte freezes,
four-method hash equality, fairness rejection, status publication, and a real
SKY130 OP+AC+transient OTA evaluation.

The final repository-wide verification completed with 289 passed and 1
pre-existing conditional skip; the skipped Task 3 test requires the external
SKY130_MODEL_LIBRARY environment variable.

## Known limitations

- Only TT at 27 C is included; there is no PVT optimization or mismatch.
- Biases are ideal voltage sources rather than an on-chip bias generator.
- The OTA is single-ended and has no CMRR benchmark or common-mode feedback.
- Settling time is not a hard metric because its semantics were not frozen.
- Layout parasitics and package/load variation are absent.
- The 12-dimensional prior contains a very sparse all-device-valid region.
- Ten seeds support descriptive baselines, not high-power ranking claims.
- Independent processes expose realistic current tooling cost but do not
  isolate model loading from numerical solution time.

## Recommendation for Task 8

Keep this Task 7 benchmark and all hashes immutable. Pre-register a separate
Task 8 comparison between this Full-only reference and staged early
rejection. The 98.8% aggregate OP-invalid rate creates a strong opportunity
to avoid AC and transient work, while the measured per-analysis and
model-free launch profiles make wall-clock crossover directly testable.
Task 8 should retain paired seeds, exact analysis/process accounting, and
candidate-count survival, while adding analysis-cost and wall-time survival.
It must report any false-rejection risk and should make no speedup claim until
measured end to end.
