# Frozen Common-Source Amplifier Benchmark

Status: frozen for Research Task 3  
Freeze timestamp: 2026-08-07T08:20:00Z  
Freeze Git commit: `51ac2714df4c5fc8661ec0fedd06c3447e4c21e9`  
Benchmark configuration SHA-256: `d60664b436ce9a928da2db86ca83378d556f18ddcf54b633394609f67288bec9`

## Topology and model

The benchmark is a resistively loaded, inverting NMOS common-source amplifier:
VDD → RD → VOUT → NMOS → ground. VIN is a DC bias plus a 1 V AC small-signal
source. CL connects VOUT to ground. Every candidate is one combined real
ngspice process containing `.op` followed by `.ac`.

The frozen model is `N1`, the BSIM3 3.3 reference NMOS model copied byte for
byte from `examples/mos/modelcard.nmos` in the official ngspice 46 Windows
binary distribution. SHA-256:
`e14792f8adbe569d6f4152292343bc9fb0a41364a5aa1a5ad476b82f70316168`.
This is not SKY130 and is not represented as a foundry PDK. No SKY130
installation was present during Task 3. The typed model interface accepts an
external YAML/environment-resolved SKY130 library, but missing libraries fail
explicitly and never fall back to this reference model.

## Fixed conditions

- VDD: 1.8 V
- CL: 1 pF
- temperature: 27 °C
- AC sweep: 10 Hz to 1 GHz, 30 points/decade
- model corner label: `reference` (no `.lib` section)
- PVT configuration: explicitly empty; PVT optimization is outside Task 3

## Search variables and rationale

The four variables are W, L, RD, and VBIAS. Keeping L variable makes the first
nonlinear benchmark expose transconductance/output-resistance and capacitance
tradeoffs instead of reducing the task to bias and load selection.

| Variable | Frozen range | Sampling | Unit | Declared technology guardrail |
|---|---:|---|---|---:|
| `width_m` | 2–100 µm | log | m | 0.5–200 µm |
| `length_m` | 0.5–2 µm | linear | m | 0.3–10 µm |
| `drain_resistance_ohm` | 2–50 kΩ | log | Ω | 0.1–1000 kΩ |
| `input_bias_v` | 0.65–1.2 V | linear | V | 0–1.8 V |

All four optimizers receive this identical search space. The guardrails are
conservative limits for this reference-model benchmark, not SKY130 design
rules.

## Measurements

- `gain_db`: first-frequency `vdb(out)` magnitude. Because `vdb` uses complex
  magnitude, the approximately ±180° inverting phase does not turn gain into a
  signed voltage gain. A negative dB value still correctly means attenuation.
- `bandwidth_hz`: first post-peak crossing 3 dB below peak, interpolated on log
  frequency.
- `dc_power_w`: `abs(VDD * I(VDD))` from `.op`; `derived_rc_power` is forbidden.
- `output_dc_voltage`: `.op` `V(out)`.
- evidence also records VDD, VIN, IDD and, for this model, VGS, VDS, gm, gds,
  Vth, and VDSAT. `region` is unsupported by the current model/output interface
  and is not fabricated.

## Frozen specification and success

A candidate is feasible only when all constraints hold simultaneously:

- gain ≥ 8 dB
- bandwidth ≥ 10 MHz
- DC power ≤ 350 µW
- 0.3 V ≤ VOUT_DC ≤ 1.5 V

`is_feasible` is this conjunction, never a scalar-objective threshold.

For every lower bound T, normalized violation is
`max(0, (T - actual) / abs(T))`; for every upper bound it is
`max(0, (actual - T) / abs(T))`. Total violation is the unweighted sum of all
five terms. `ObjectiveEvaluator` alone applies these formulas for every method.

The common scalar feedback is lexicographic:

- infeasible: `objective = 1 + total_constraint_violation`
- feasible: `objective = P_DC / (350e-6 + P_DC)`

Thus every feasible point ranks ahead of every infeasible point; among feasible
points lower measured supply power is preferred. Random, DE, TPE, and BO use
exactly this formulation.

## Calibration and freeze basis

The predeclared 81-point deterministic grid made 81 real ngspice calls. 68
points produced complete metrics; 13 explicitly failed bandwidth analysis
because no post-peak −3 dB crossing occurred before 1 GHz. No bandwidth was
imputed. Successful ranges were gain −49.9167–23.2123 dB, bandwidth
3.1126–910.3693 MHz, power 0.1388 µW–1.4895 mW, and VOUT
0.01746–1.79985 V. Five of all 81 points (6.17%) meet the frozen constraints,
which establishes feasibility without making random success trivial.

The raw and annotated rows are in `common_source_calibration.csv`. They are
excluded from all baseline statistics and optimizer plots.
