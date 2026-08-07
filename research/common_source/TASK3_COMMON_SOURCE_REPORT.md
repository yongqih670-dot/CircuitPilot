# Research Task 3 — Common-Source Report

Status: complete. Benchmark semantics were frozen before both clean-worktree
smoke and baseline execution.

## Reproducible design definition

- topology: resistively loaded NMOS common-source amplifier with 1 pF output load
- model: ngspice 46 reference BSIM3 `N1` (not SKY130)
- model SHA-256: `e14792f8adbe569d6f4152292343bc9fb0a41364a5aa1a5ad476b82f70316168`
- model provenance: official ngspice 46 binary, `examples/mos/modelcard.nmos`
- supply/temperature: 1.8 V / 27 °C
- search variables: W, L, RD, VBIAS; ranges are in `COMMON_SOURCE_BENCHMARK.md`
- benchmark hash: `d60664b436ce9a928da2db86ca83378d556f18ddcf54b633394609f67288bec9`
- frozen constraints: gain ≥ 8 dB, BW ≥ 10 MHz, power ≤ 350 µW,
  0.3 V ≤ VOUT ≤ 1.5 V
- success: all five constraints, with no scalar substitution for feasibility

## Calibration

The deterministic calibration used 81 independent real ngspice `.op + .ac`
calls. 68 completed all measurements and 13 were retained as analysis failures
(no −3 dB crossing by 1 GHz). The calibration CSV contains all rows and points
to each evidence directory. Frozen-spec feasibility is 5/81 (6.17%). Calibration
is not included in baseline statistics.

## Smoke Validation

Run directory:
`research_runs/task3_common_source_smoke/cp-20260807T082352367430Z-3f967f1d65bc`

- methods: Random, DE, TPE, BO
- seeds: 0, 1, 2
- budget: 25 per run
- runs/evaluations/ngspice calls: 12 / 300 / 300
- complete metric evaluations: 219
- explicit analysis failures: 81
- evidence: 300 netlists, logs, AC outputs, DC outputs, and MOS OP outputs
- fairness: passed with clean Git commit `99b2199ef4ea2cc232716943af599391fbe3c5d0`
- run success rates: Random 100%, DE 66.7%, TPE 66.7%, BO 33.3%

Smoke was used only to validate the nonlinear pipeline and did not change any
frozen benchmark field.

## Formal Baseline Experiment

Run directory:
`research_runs/task3_common_source_baseline/cp-20260807T082454433891Z-90b806b36b15`

- methods: Random, DE, TPE, BO
- seeds: 0–9
- budget: 50 per run
- runs/evaluations/ngspice calls: 40 / 2000 / 2000
- complete metric evaluations: 1573
- `analysis_failed`: 427 (no post-peak −3 dB crossing by 1 GHz)
- ngspice process failures/timeouts/nonzero exits: 0 / 0 / 0
- evidence: 2000 netlists, 2000 logs, 2000 AC outputs, 2000 DC outputs,
  and 2000 MOS operating-point outputs (40.4 MB locally)
- fairness: passed; every row carries the frozen benchmark hash, phase
  `baseline`, and identical environment/model signature

| Method | Success rate | Median best objective | Mean ± population SD | Median first feasible | Censored | Median violation | Fail rate | Calls |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Random | 1.00 | 0.192660 | 0.196804 ± 0.063893 | 7.5 | 0 | 0 | 0.022 | 500 |
| DE | 1.00 | 0.183283 | 0.200297 ± 0.093140 | 7.5 | 0 | 0 | 0.032 | 500 |
| TPE | 0.90 | 0.138396 | 0.333659 ± 0.536633 | 8 | 1 | 0 | 0.192 | 500 |
| BO | 0.40 | 1.011183 | 0.764325 ± 0.374411 | 5 (observed only) | 6 | 0.011183 | 0.608 | 500 |

Failure counts were Random 11, DE 16, TPE 96, and BO 304; all were retained
without penalties or synthetic physical metrics. The optimizers receive only a
generic success/failure status, not a failure type-specific policy.

For best-by-common-objective records, the method-level extrema were:

| Method | Best gain (dB) | Best bandwidth (Hz) | Lowest power (W) |
|---|---:|---:|---:|
| Random | 17.2272 | 1.54607e7 | 4.91636e-5 |
| DE | 16.6106 | 4.47690e7 | 3.77157e-5 |
| TPE | 15.7879 | 4.15738e7 | 4.13164e-5 |
| BO | 22.0269 | 7.05917e7 | 4.71895e-5 |

These single metrics are descriptive only. No superiority claim is made from a
single column, and Task 3 does not include statistical significance testing.
Canonical smoke/baseline tables, fairness signatures, and eight real-data plots
are published under `research/common_source/results/`.

## Verification

- complete test suite: `177 passed, 1 skipped in 11.39s`
- real-ngspice integration selection: `18 passed, 1 skipped, 159 deselected in 8.59s`
- skipped test: optional SKY130 integration because `SKY130_MODEL_LIBRARY` is
  not configured
- clean environment: PASS in a newly created venv using
  `requirements-research.lock`; `pip check` passed and a real ngspice RC
  optimization completed with 10/10 successful evaluations
- clean locked versions included Python 3.12.7, NumPy 2.5.1, SciPy 1.18.0,
  PyYAML 6.0.3, Optuna 4.9.0; baseline runs used the consistently fingerprinted
  local NumPy 1.26.4 and SciPy 1.13.1 environment
- ngspice: version 46, executable SHA-256
  `86c9ea5f645ca919e305639fa7bdb522355364c424d14e197f1ade617feb3453`

## Known limitations

SKY130 is not installed/configured in this environment. The optional integration
test is therefore expected to report a transparent skip. This benchmark proves
the transistor-level infrastructure with a content-locked real BSIM3 model, but
its numbers must not be interpreted as SKY130 silicon performance.

The benchmark has no extracted layout parasitics or process/voltage/temperature
corners. `region` is unsupported; VGS, VDS, gm, gds, Vth, and VDSAT are available
for the frozen primitive model. A finite 1 GHz AC stop frequency makes
above-range bandwidth an explicit analysis failure; this is intentionally not
imputed and exposes substantial censored/failure behavior, particularly for BO.
Task 3 does not implement Pareto optimization or significance tests.

## Next-stage recommendation

Preserve this hash and raw failure evidence. Before failure-aware or PVT-aware
research, install and content-lock a specific SKY130 release, create a new
calibration/freeze hash, and pre-register how no-crossing and simulator failures
are treated. Do not retroactively modify or reinterpret this Task 3 baseline.
