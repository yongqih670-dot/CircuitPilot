# Research Task 5: SKY130 Differential-Amplifier Benchmark

## Outcome

Task 5 is complete and frozen. CircuitPilot now has a second independent
transistor-level SKY130 benchmark: a real five-transistor differential
amplifier with role-based matched sizing, explicit MOS terminals, direct
differential-mode and common-mode AC measurements, truthful CMRR lower-bound
semantics, bandwidth right-censoring, real operating-point power and device
physics, fair Random/DE/TPE/BO baselines, and Kaplan-Meier/RMST outputs.

No LLM Agent, failure-aware optimization policy, PVT optimization, mismatch
Monte Carlo, two-stage OTA, topology generation, layout/parasitics, or Web UI
was introduced. Task 4 remains immutable at benchmark hash
1a577200d71a900eb8ffec3fe680e3dd53e0298e87692dc66f407481de46c664.

## Technology provenance

| Field | Frozen value |
|---|---|
| Source | FOSSi Foundation Ciel/Open_PDKs prebuilt SKY130A |
| Open_PDKs release | 1.0.606 |
| Open_PDKs commit | 026824c7969ce6f4fc9678e6ca04b0a06a596c4b |
| Primitive commit | 403964dc7f9cca5ec1a8cc7b4f2a6f532b781676 |
| Devices | sky130_fd_pr__nfet_01v8 and sky130_fd_pr__pfet_01v8 |
| Corner | TT |
| Model-tree SHA-256 | d88fa42b4f42f7b1f6987141aa92161865cfc9ff5fbdce9bbc9f137bde3a2f61 |
| Model files | 840 |
| Top-library SHA-256 | 17c208a699228f5acb87bf59c09c22a4c4d3937b6766b4957737d34e8e075f64 |
| ngspice | ngspice-46 : Circuit level simulation program |
| ngspice executable SHA-256 | 86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453 |
| Formal execution commit | 04cfb078728dcfb9b42c95be80c5176eba103591 |

The model path is resolved from the frozen configuration and verified by
content. A missing or mismatched tree is an explicit error; no Task 3 model or
synthetic device is used.

## Topology and device mapping

The circuit is the conventional five-transistor, single-ended topology:
NMOS M1/M2 differential pair, 1:1 PMOS current-mirror active load, and an
NMOS voltage-biased tail current source. VDD is 1.8 V, input common mode is
0.9 V, load capacitance is 50 fF, and temperature is 27 C.

| Role | Device | D / G / S / B | Shared sizing |
|---|---|---|---|
| input_m1 | NMOS | mirror / VINP / tail / GND | input pair W/L |
| input_m2 | NMOS | VOUT / VINN / tail / GND | input pair W/L |
| load_mirror | PMOS | mirror / mirror / VDD / VDD | active-load W/L |
| load_output | PMOS | VOUT / mirror / VDD / VDD | active-load W/L |
| tail | NMOS | tail / tail-bias / GND / GND | tail W/L |

All drain, gate, source, and bulk terminals are explicit. Symmetry and the
1:1 mirror relationship are guaranteed by design-variable mapping, not left
to optimizer coincidence.

## Search dimensions and rationale

The frozen search has seven role variables.

| Variable | Range | Sampling | Matching and expected influence |
|---|---:|---|---|
| input_pair_width_m | 0.84-10 um | log | M1=M2; gm, capacitance, gain, bandwidth |
| input_pair_length_m | 0.15-0.80 um | linear | M1=M2; output resistance, gain, speed |
| active_load_width_m | 0.84-20 um | log | PMOS pair 1:1; current density, bias, capacitance |
| active_load_length_m | 0.15-1.00 um | linear | PMOS pair 1:1; resistance, gain, speed |
| tail_width_m | 0.42-12 um | log | tail-current capability, CMRR, power |
| tail_length_m | 0.15-1.00 um | linear | tail resistance, CMRR, headroom |
| tail_bias_v | 0.55-1.00 V | linear | current, headroom, power, operating region |

The full design prior is recorded in SEARCH_SPACE_RATIONALE.md and was
written before calibration.

## Testbenches and measurement semantics

Two electrically isolated circuit copies use identical candidate sizing in
one netlist and one ngspice process.

- Differential mode uses VINP = 0.5 at 0 degrees and VINN = 0.5 at
  180 degrees, giving a unit differential input. Ad is read directly from
  that output.
- Common mode uses VINP = VINN = 1 at 0 degrees. Acm is read directly from
  that output.

The AC window is fixed at 10 Hz-10 GHz with 30 points per decade. Differential
bandwidth uses post_peak_minus_3db_right_censoring_v1. A real post-peak
-3 dB crossing is log-frequency interpolated and measured exactly. No crossing
by 10 GHz records right_censored and a 10 GHz lower bound; it is not a failure
or an invented exact bandwidth.

CMRR uses direct_ad_acm_floor_lower_bound_v1. For reliable responses,
CMRR_dB = Ad_dB - Acm_dB. If Acm is at or below the frozen -120 dB floor, the
record stores cmrr_status=lower_bound and a conservative lower bound; it never
stores infinity or a fabricated exact result. Exact and lower-bound values may
prove greater-equal constraints under the common evaluator but remain
separate physical fields.

DC power is abs(1.8 V times I(VDD_D)) from the real differential-copy
operating point. Output DC voltage and absolute tail-sense current are also
recorded. For each of five critical MOS devices, VGS, VDS, VTH, gm, gds, and
VDSAT are parsed. NMOS validity is VGS > VTH and VDS >= VGS - VTH. PMOS
validity applies the equivalent magnitude condition VSG > abs(VTH) and
VSD >= VSG - abs(VTH). The candidate is operating-region valid only when all
five devices pass; no simulator region enum is trusted.

## Cost, feasibility, and objective

The primary fair budget unit is one candidate evaluation. Every candidate
uses one ngspice process containing one operating-point solve and one combined
AC solve over the two isolated testbench copies. It records one candidate,
one ngspice process call, two physical analysis calls, and two logical AC
testbenches.

Feasibility is strictly the conjunction of all hard constraints. The common
normalized violation is minimized first. Only after feasibility does the
frozen lexicographic secondary objective minimize real DC supply power.
An attractive scalar objective never implies feasibility.

The taxonomy records simulation_failed, dc_non_convergence,
differential_ac_error, common_mode_ac_error,
invalid_differential_response, invalid_common_mode_response,
bandwidth_right_censored, cmrr_lower_bound, and
operating_region_invalid. Task 5 records these states but implements no
failure-aware policy.

## Calibration and benchmark freeze

The protocol, feasible-density target, ladder, objective, and budget rule were
committed before calibration at
ca7e7fb634b27458195b18745e66db7be4ad7bb9. Calibration used the first 256
points of an unscrambled seven-dimensional Sobol sequence, with seed metadata
0 and no optimizer feedback or adaptive replacement.

All 256 candidates completed: 256 processes, 512 physical analyses, no process
or measurement failures, 256 exact bandwidths, no bandwidth censoring, 256
exact CMRRs, no CMRR lower bounds, and 40 operating-region-valid candidates.
Observed medians were 33.178601 dB differential gain, 4.205083 MHz bandwidth,
55.9683463 dB CMRR, 16.3949 uW power, 0.757721 V output, 9.10829 uA tail
current, and 0.734 s runtime.

The pre-registered mechanical ladder selected row 1:

- differential gain >= 15 dB;
- differential bandwidth >= 20 MHz;
- CMRR >= 35 dB;
- DC power <= 1 mW;
- output voltage in [0.25, 1.55] V;
- all five critical devices operating-region valid.

Two of 256 candidates were feasible, or 0.78125%, inside the declared
0.5%-3.0% band. Median runtime was below the 1.5 s cutoff, so the formal budget
was frozen at 100. The Sobol design SHA-256 is
1345d5b3b4a318cbade769c1d63ec0e4b512d2817f20067b6462724597d45f25.
The semantic freeze commit is
fd16153f58b7f5445caeeb2696829d7a2e2b4d36.

Task 5 benchmark hash:
57d2183621ecf37e5ca22e012452c43fce6459be7d347a5cfc93d0b394c14378.

## Smoke validation

Accepted smoke suite: cp-20260828T082548903046Z-3c54cd6d4dbb.
Random, DE, TPE, and BO used seeds 0-2 and budget 25. The 12 runs produced
300 candidates, 300 real ngspice process calls, and 600 physical analysis
calls. All processes and measurements completed; every bandwidth and CMRR was
exact, with no failure, invalid response, right-censored bandwidth, or CMRR
lower bound.

Run success rates were Random 0.0, DE 0.3333, TPE 0.0, and BO 0.0. These are
pipeline observations only and are not used as algorithm conclusions. An
earlier diagnostic suite interrupted by a Windows Matplotlib/Tk cleanup crash
was excluded and documented in DIAGNOSTIC_RUNS.md; the Agg fix did not alter
benchmark semantics, and the accepted suite started in a new run directory.

## Formal baseline

Accepted formal suite: cp-20260828T083527262806Z-63692fed89de. All four
methods used seeds 0-9 and exactly 100 candidates per run. Fairness validation
confirmed the common clean execution commit, benchmark, topology, role
mapping, PDK/model, search space, differential/common testbenches, CMRR and
bandwidth semantics, objective, constraints, seeds, budget, and cost semantics.

| Method | Run success | Median best objective | Median violation | Events / censored | KM median | RMST | BW censored | CMRR lower bound | OP invalid | Mean run time (s) | Candidates / processes / analyses |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Random | 0.5 | 0.560516 | 0.0218035 | 5 / 5 | 98 | 79.7 | 1 | 0 | 863 | 77.7828 | 1000 / 1000 / 2000 |
| DE | 1.0 | 0.0302110 | 0 | 10 / 0 | 24 | 31.5 | 15 | 0 | 697 | 68.3498 | 1000 / 1000 / 2000 |
| TPE | 0.8 | 0.0338705 | 0 | 8 / 2 | 49 | 59.5 | 1 | 0 | 583 | 70.1031 | 1000 / 1000 / 2000 |
| BO | 0.5 | 0.595876 | 0.0573531 | 5 / 5 | 72 | 69.0 | 12 | 0 | 949 | 70.0797 | 1000 / 1000 / 2000 |

The corresponding method-level rates and mean per-candidate simulation times
are:

| Method | Candidate failure rate | OP-invalid rate | BW-censored rate | CMRR-lower-bound rate | Mean candidate time (s) |
|---|---:|---:|---:|---:|---:|
| Random | 0 | 0.863 | 0.001 | 0 | 0.742714 |
| DE | 0 | 0.697 | 0.015 | 0 | 0.647752 |
| TPE | 0 | 0.583 | 0.001 | 0 | 0.655838 |
| BO | 0 | 0.949 | 0.012 | 0 | 0.663051 |

Survival is the probability that a run has not yet found its first feasible
candidate. Unsuccessful runs are censored at exactly 100; they are not assigned
101 and are not dropped. RMST is the area under that survival curve from zero
through the fixed 100-candidate horizon. The exact time-zero/event coordinates
are published in results/baseline/kaplan_meier.csv.

There were 242 feasible candidate records: Random 6, DE 103, TPE 122, and BO
11. The following rows are each method's joint best feasible candidate under
the frozen scalar feedback, so the listed metrics belong to the same design.

| Method | Seed / iteration | Ad (dB) | BW (MHz) | CMRR (dB) | Power (uW) | VOUT (V) |
|---|---|---:|---:|---:|---:|---:|
| Random | 2 / 98 | 27.6333 | 30.1353 | 44.1311 | 46.2700 | 0.470774 |
| DE | 2 / 97 | 17.1992 | 21.3519 | 48.8262 | 13.6212 | 1.081714 |
| TPE | 3 / 63 | 17.8988 | 21.1771 | 42.3568 | 16.7434 | 1.037108 |
| BO | 8 / 13 | 24.7933 | 33.3451 | 45.3692 | 42.2047 | 0.930447 |

With ten seeds, these are descriptive baseline results rather than broad
significance claims.

## Complete cost and status audit

The 40 formal runs contain exactly 4,000 candidates, 4,000 ngspice process
calls, and 8,000 physical analysis calls. All 4,000 simulation statuses are
success, all 4,000 measurement statuses are complete, and all failure_type
fields are empty.

| Method | Exact BW | BW right-censored | Exact CMRR | CMRR lower bound | OP valid | OP invalid | Candidate failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| Random | 999 | 1 | 1000 | 0 | 137 | 863 | 0 |
| DE | 985 | 15 | 1000 | 0 | 303 | 697 | 0 |
| TPE | 999 | 1 | 1000 | 0 | 417 | 583 | 0 |
| BO | 988 | 12 | 1000 | 0 | 51 | 949 | 0 |
| Total | 3971 | 29 | 4000 | 0 | 908 | 3092 | 0 |

Right-censored bandwidth is a successful bounded measurement, not a candidate
failure. No simulation_failed, dc_non_convergence, differential_ac_error,
common_mode_ac_error, invalid differential/common response, analysis error, or
CMRR lower-bound event occurred in the formal data.

## Tests and evidence

Final complete pytest result:

    216 passed, 1 skipped in 16.00s

The suite covers NMOS differential-pair and PMOS active-load topology,
explicit bulk terminals, matched role mapping, both AC testbenches,
differential/common gain and CMRR extraction, numerical CMRR edge cases and
lower bounds, bandwidth censoring, tail current, real supply power,
operating-region physics, cost accounting, topology/CMRR hash sensitivity,
the unchanged Task 4 hash, common four-optimizer hash, deterministic Sobol
calibration, and a real SKY130 differential-amplifier E2E. The single skip is
the older optional Task 3 SKY130_MODEL_LIBRARY environment probe; Task 5 uses
its frozen YAML model path and its real E2E ran.

Published formal CSV, fairness JSON, Kaplan-Meier CSV, and plots are under
results/baseline. Raw accepted calibration, smoke, and formal directories are
preserved as ZIP archives with byte hashes in
results/evidence_archives/EVIDENCE_ARCHIVES.md. The formal archive SHA-256 is
f9c31ef42f374de7332bbbbc65e272460fc0e553849e7865fa14ef442dd39883.

## Known limitations and next stage

- This is a single-ended five-transistor amplifier at nominal TT, 1.8 V,
  27 C; no PVT, mismatch, noise, transient slew, phase margin, or load sweep
  is included.
- The two isolated copies share sizing but not random mismatch, which is
  deliberately outside this benchmark.
- Bandwidth beyond 10 GHz remains a lower bound; common-mode gain below
  -120 dB produces only a CMRR lower bound.
- The operating-region test is a transparent voltage inequality, not a full
  analog robustness or reliability proof.
- BO's behavior is characterized only at these ten seeds and this finite
  budget.
- The local PDK is not committed because of size; exact provenance and content
  hashes are required for reproduction.

Task 5 should now remain immutable. A next research stage may use this recorded
taxonomy for a separately pre-registered PVT, mismatch, or failure-aware study,
but it must create a new benchmark hash and must not reinterpret Task 4 or
Task 5 evidence.
