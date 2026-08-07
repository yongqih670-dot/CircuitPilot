# Research Task 3 — Common-Source Report

Status: implementation and benchmark freeze complete; smoke/baseline results
will be appended only after clean-worktree execution.

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

## Pending clean-run evidence

The final report will record smoke validation, ten-seed baseline statistics,
per-method ngspice calls, simulation/analysis failures, plots, full test output,
clean-environment output, known limitations, and the next-stage recommendation.
No algorithm conclusion is made before those runs.

## Known limitation before execution

SKY130 is not installed/configured in this environment. The optional integration
test is therefore expected to report a transparent skip. This benchmark proves
the transistor-level infrastructure with a content-locked real BSIM3 model, but
its numbers must not be interpreted as SKY130 silicon performance.
