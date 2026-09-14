# SKY130 Common-Source Benchmark 2.0

Status: frozen before optimizer validation.  
Benchmark hash: `1a577200d71a900eb8ffec3fe680e3dd53e0298e87692dc66f407481de46c664`  
Semantic-freeze commit: `a9231a82876d8b5fc4f0bb725631aff3b3a8230b`

This benchmark is independent of the immutable Task 3 reference-BSIM3
benchmark.  Task 3 retains hash
`d60664b436ce9a928da2db86ca83378d556f18ddcf54b633394609f67288bec9`
and its original 1 GHz no-crossing behavior.  Task 4 data must never be used to
retroactively reinterpret Task 3 records.

## Content-locked technology

- source: FOSSi Foundation Ciel/Open_PDKs prebuilt SKY130A;
- Open_PDKs release: `1.0.606`;
- Open_PDKs commit: `026824c7969ce6f4fc9678e6ca04b0a06a596c4b`;
- primitive-library commit: `403964dc7f9cca5ec1a8cc7b4f2a6f532b781676`;
- device: `sky130_fd_pr__nfet_01v8`;
- corner: TT;
- model-tree files: 840;
- model-tree SHA-256: `d88fa42b4f42f7b1f6987141aa92161865cfc9ff5fbdce9bbc9f137bde3a2f61`;
- top library SHA-256: `17c208a699228f5acb87bf59c09c22a4c4d3937b6766b4957737d34e8e075f64`.

The resolved path may come from YAML, `SKY130_PDK_ROOT`, or
`SKY130_MODEL_LIBRARY`; path text is not identity.  The two content hashes are
verified when the config loads and are bound into the benchmark hash.  Missing
or changed content is an explicit error.  There is no N1/reference-model
fallback.

## Circuit and measurement window

The topology is `VDD -> RD -> VOUT -> NMOS -> GND`.  The device invocation has
explicit drain, gate, source, and bulk terminals; source and bulk are grounded.
`VIN` is the candidate DC bias plus AC magnitude 1.  Fixed conditions are:

- VDD: 1.8 V;
- load capacitance: 20 fF;
- temperature: 27 °C;
- AC sweep: 10 Hz to 10 GHz, 30 points/decade;
- one ngspice process per candidate containing both `.op` and `.ac`.

The fixed window is identical for all candidates and methods.  Candidate-wise
adaptive sweep expansion is forbidden in this benchmark.

## Search space

| Parameter | Range | Scale |
|---|---:|---|
| `width_m` | 0.42–7.0 µm | log |
| `length_m` | 0.15–1.0 µm | linear |
| `drain_resistance_ohm` | 2–100 kΩ | log |
| `input_bias_v` | 0.55–1.05 V | linear |

Technology-aware reasons and guardrails are in `SEARCH_SPACE_RATIONALE.md`.
All four optimizers use this exact space.

## Physical metrics

- `gain_db`: parsed low-frequency AC gain;
- `bandwidth_hz`: exact log-frequency interpolation of the post-peak -3 dB
  crossing, or null when not observed;
- `dc_power_w`: `abs(VDD * I(VDD))` using parsed `.op` values;
- `output_dc_voltage`: parsed `V(out)`;
- `VGS`, `VDS`, `VTH`, `gm`, and `gds`: parsed SKY130 MOS operating-point
  vectors;
- `operating_region_valid = 1` exactly when `VGS > VTH` and
  `VDS >= VGS - VTH`, otherwise 0.

No physical metric may be synthesized, defaulted, or taken from an optimizer.

## Bandwidth semantics

Semantics version: `post_peak_minus_3db_right_censoring_v1`.  
Censoring policy: `fixed_window_right_censored_lower_bound_v1`.

Valid AC data with no post-peak -3 dB crossing by 10 GHz is recorded as:

```text
bandwidth_status = right_censored
bandwidth_hz = null
bandwidth_lower_bound_hz = 1e10
```

This is a complete measurement and a successful ngspice evaluation, not a
simulation failure.  The lower bound can prove a `bandwidth_hz >= threshold`
constraint, but it is never reported as an exact bandwidth.  Invalid gain
reference, analysis error, and ngspice process failure remain separate states.

## Frozen specification

- gain >= 14 dB;
- bandwidth >= 200 MHz, with the right-censored lower-bound rule above;
- DC supply power <= 0.5 mW;
- 0.3 V <= output DC voltage <= 1.5 V;
- `operating_region_valid >= 1`;
- scalar objective: minimize DC supply power after normalized hard-constraint
  feasibility.

The deterministic 256-point calibration found 5 feasible points (1.953125%),
inside the pre-registered 1%–3% band.  Formal budget therefore remained 50.
Changing the model, search space, circuit, specification, measurement window,
metric definitions, or censoring semantics requires a new benchmark hash.
