# Research Task 4: SKY130 Common-Source Benchmark 2.0

## Outcome

Task 4 is complete.  CircuitPilot now has an independent, content-locked
SKY130 common-source benchmark with real `.op + .ac`, real supply-current
power, explicit MOS terminals, truthful bandwidth right-censoring, fair
Random/DE/TPE/BO baselines, and survival-ready result files.  No mock, renamed
N1 model, synthetic physical metric, default bandwidth, adaptive candidate
sweep, PVT strategy, failure-aware optimizer, or LLM Agent was used.

Task 3 remains immutable with benchmark hash
`d60664b436ce9a928da2db86ca83378d556f18ddcf54b633394609f67288bec9`.
Its old 1 GHz no-crossing `analysis_failed` records and raw results were not
modified or reinterpreted.

## Technology and execution provenance

| Field | Frozen value |
|---|---|
| Source | FOSSi Foundation Ciel/Open_PDKs prebuilt SKY130A |
| Open_PDKs release | `1.0.606` |
| Open_PDKs commit | `026824c7969ce6f4fc9678e6ca04b0a06a596c4b` |
| Primitive commit | `403964dc7f9cca5ec1a8cc7b4f2a6f532b781676` |
| Device | `sky130_fd_pr__nfet_01v8` |
| Corner | TT |
| Model-tree SHA-256 | `d88fa42b4f42f7b1f6987141aa92161865cfc9ff5fbdce9bbc9f137bde3a2f61` |
| Model files | 840 |
| Top-library SHA-256 | `17c208a699228f5acb87bf59c09c22a4c4d3937b6766b4957737d34e8e075f64` |
| ngspice | `ngspice-46 : Circuit level simulation program` |
| ngspice executable SHA-256 | `86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453` |
| Formal execution commit | `5d6637334943de5e9b05e3bc33f56b906b3deb02` |

The model is resolved from explicit YAML or the documented SKY130 environment
variables, then verified by bytes.  A missing or mismatched model is an
explicit error; fallback to Task 3 N1 is forbidden.

## Circuit, search space, and measurements

The topology is `VDD -> RD -> VOUT -> NMOS -> GND`.  Drain, gate, source, and
bulk are explicit; source and bulk are grounded.  Conditions are VDD 1.8 V,
CL 20 fF, TT at 27 °C, and a fixed 10 Hz–10 GHz sweep with 30 points/decade.
Every candidate uses exactly one real ngspice process containing `.op` and
`.ac`.

The common search space is W 0.42–7.0 µm (log), L 0.15–1.0 µm (linear), RD
2–100 kΩ (log), and VBIAS 0.55–1.05 V (linear).  The complete rationale is in
`SEARCH_SPACE_RATIONALE.md`.

DC power is `abs(VDD * I(VDD))` from parsed operating-point data.
`operating_region_valid` is the recorded physical condition
`VGS > VTH and VDS >= VGS - VTH`, using parsed SKY130 MOS vectors.  It is not a
model-provided region label.

## Bandwidth semantics

The frozen semantics version is
`post_peak_minus_3db_right_censoring_v1`; the censoring policy is
`fixed_window_right_censored_lower_bound_v1`.

- A valid post-peak -3 dB crossing is log-frequency interpolated and stored as
  exact `bandwidth_hz`.
- A valid response with no crossing by 10 GHz stores
  `bandwidth_status=right_censored`, `bandwidth_hz=null`, and
  `bandwidth_lower_bound_hz=1e10`.
- The lower bound can prove a `bandwidth >= threshold` hard constraint but is
  never presented as an exact bandwidth.
- `invalid_response`, `analysis_error`, and `simulation_failed` remain distinct.

## Calibration and benchmark freeze

The protocol and threshold ladder were committed before calibration at
`f555479590b713d77bba6ab430a2d935a77495c6`.  A deterministic 4x4x4x4 grid
launched 256 real ngspice processes: 256 succeeded, 0 failed, 192 bandwidths
were exact, and 64 were right-censored.

The calibration observed gain from -52.6023694 to 24.6031543 dB, exact
bandwidth from 72.7508374 MHz to 9.38679613 GHz, power from 88.9033284 nW to
1.19932502 mW, and VOUT from 0.00417820 to 1.79990106 V.

The pre-registered rule selected gain >= 14 dB, bandwidth >= 200 MHz, power <=
0.5 mW, VOUT in [0.3, 1.5] V, and valid operating region.  Five of 256 grid
points were feasible: 1.953125%, inside the declared 1%–3% difficulty band.
The formal budget therefore remained 50.

Benchmark 2.0 hash:
`1a577200d71a900eb8ffec3fe680e3dd53e0298e87692dc66f407481de46c664`.
The semantic freeze commit is `a9231a82876d8b5fc4f0bb725631aff3b3a8230b`.

## Smoke validation

Accepted smoke run: `cp-20260807T111655257288Z-cbeae67e02e6`.

- methods: Random, DE, TPE, BO;
- seeds: 0, 1, 2;
- budget: 25 per run;
- 12 runs, 300 records, 300 real ngspice calls;
- 300 process successes and 300 complete measurements;
- 262 exact bandwidths and 38 right-censored bandwidths;
- 0 ngspice failures, 0 analysis errors, 0 invalid responses.

Smoke run success rates were Random 1.0, DE 0.667, TPE 1.0, and BO 0.667.
These are validation observations only and are not used as algorithm claims.

## Formal baseline

Accepted formal suite: `cp-20260807T112328876830Z-afedfa321406`.
All methods used seeds 0–9 and budget 50.  Fairness validation records a clean
worktree, the common benchmark/model hashes, the same PDK, window, objectives,
constraints, seed set, Simulator, Analyzer, and measurement semantics.

| Method | Success rate | Median best objective | Median violation | Events / censored | KM median | RMST | Right-censored BW | Exact BW | Mean runtime (s) | Calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Random | 1.0 | 0.0812656 | 0 | 10 / 0 | 15 | 13.3 | 53 | 447 | 26.5203 | 500 |
| DE | 1.0 | 0.0688198 | 0 | 10 / 0 | 9 | 11.8 | 55 | 445 | 25.5811 | 500 |
| TPE | 1.0 | 0.0587232 | 0 | 10 / 0 | 11 | 11.9 | 31 | 469 | 25.7780 | 500 |
| BO | 0.8 | 0.106109 | 0 | 8 / 2 | 29 | 26.7 | 68 | 432 | 27.5453 | 500 |

Overall there are 40 runs, 2,000 records, and exactly 2,000 real ngspice
calls.  All 2,000 processes succeeded and all 2,000 measurements completed.
There are 1,793 exact bandwidths and 207 right-censored bandwidths.  The
ngspice failure, analysis error, and invalid-response rates are all zero.

Formal extrema reported by the common summary are:

| Method | Best gain (dB) | Best exact bandwidth (Hz) | Best BW lower bound (Hz) | Best power (W) |
|---|---:|---:|---:|---:|
| Random | 18.9586 | 9.19887934e9 | 1.0e10 | 2.92764119e-5 |
| DE | 21.7699 | 7.57594353e9 | 1.0e10 | 2.29484407e-5 |
| TPE | 21.6710 | 6.20718447e9 | 1.0e10 | 1.94017860e-5 |
| BO | 17.7489 | 8.18996150e9 | 1.0e10 | 2.36197373e-5 |

These extrema need not belong to one joint candidate.  With only ten seeds,
the table is descriptive; no exaggerated significance claim is made.

## Censored-data outputs

`results/baseline/kaplan_meier.csv` contains the exact time-zero and event-time
coordinates: method, simulation evaluations, survival probability, at risk,
events, censored, horizon, RMST, and KM median.  The matching
`kaplan_meier_time_to_feasible.png` is generated only from canonical
`evaluations.csv`.  Survival is the probability that a run has not yet found a
feasible candidate.  RMST is the area under that survival curve from evaluation
0 through the fixed budget horizon 50.

Unsuccessful BO runs remain `simulations_to_first_feasible=null`, with
`event_observed=false`, `evaluation_time=50`, and `budget_at_censoring=50`.
They are not replaced by 51 or dropped from KM/RMST.

## Tests and issues found

Final complete pytest output:

```text
........................................................................ [ 36%]
........................................................................ [ 73%]
..................................s..................                    [100%]
SKIPPED [1] tests/test_task3_benchmark.py:76: SKY130_MODEL_LIBRARY is not configured
196 passed, 1 skipped in 11.61s
```

The real Task 4 SKY130 E2E, real supply-current power assertion, model hash,
bulk-terminal netlist, long Windows path, exact/censored bandwidth, lower-bound
constraint, four-method hash, Task 3 hash, and KM tests all passed.  The single
skip is an older optional Task 3 environment-variable probe; Task 4 uses its
frozen YAML path and was executed.

Smoke exposed two infrastructure defects before accepted formal execution:
floating-point endpoint overshoot and Windows path length.  Both were fixed,
tested, committed, and the affected suites were restarted from new unique run
directories.  `DIAGNOSTIC_RUNS.md` records the excluded run IDs.  Two initial
full-test invocations also used unsuitable temporary paths (one containing
spaces, one with inaccessible ACLs); the final explicit no-space temporary
directory run above is the valid complete result.

## Evidence and reproducibility

Accepted calibration, smoke, and formal raw directories remain under
`research_runs/`.  Git-tracked ZIP archives and their SHA-256 values are listed
in `results/evidence_archives/EVIDENCE_ARCHIVES.md`.  Published result folders
include run-level results, method summaries, fairness JSON, Kaplan–Meier CSV,
and all plots.

## Known limitations and next-stage recommendation

- This is one resistor-loaded NMOS common-source topology at nominal TT,
  1.8 V, and 27 °C; it is not a differential amplifier or OTA.
- No PVT sweep, mismatch, layout parasitic, noise, slew, phase margin, or
  reliability analysis is included.
- Bandwidth above 10 GHz remains a lower bound by design; exact values require
  a separately pre-registered wider-window benchmark.
- The operating-region condition is an explicit voltage inequality, not a
  trusted simulator region enum.
- The local PDK is not committed because of size; exact provenance and content
  hashes are mandatory for reproduction.
- Ten formal seeds support baseline characterization, not broad statistical
  claims.

The next research task should build on this frozen benchmark without mutating
its hash or evidence.  A future PVT/failure-aware study should first
pre-register corners, failure taxonomy, cost accounting, and comparison rules;
it should reuse the same Simulator/Analyzer boundary and censored-data outputs.
