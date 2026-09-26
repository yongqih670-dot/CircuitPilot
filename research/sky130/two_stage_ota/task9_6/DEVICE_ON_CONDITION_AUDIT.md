# Task 9.6 device-on condition audit — real Benchmark v2

The Task 9.5 best 12/15 design was rerun fresh: all 15 corners and
45 OP/AC/transient analyses completed without analysis error.
Exact robust violation is 1.02250476; 12/15 corners pass. The three preidentified failing corners were
retained and independently probed for signed model Id, mirror node and
external terminal coordinates (three additional charged processes).
Raw evidence is in the two CRC-checked local audit archives and the
machine-readable Full matrix. No v2 predicate was changed.

## Stage and frozen hard-spec evidence

| Corner | Gain dB | UGF MHz | PM ° | Power mW | Output V | +slew V/µs | −slew V/µs | Failed hard components |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ss__high_v_low_t | 75.725 | 1.3817 | 86.541 | 0.2389 | 0.54201 | 0.61158 | 0.58131 | operating_region |
| fs__nominal | 73.239 | 1.6961 | 85.614 | 0.22811 | 1.0543 | 0.83483 | 0.78725 | operating_region |
| fs__high_v_low_t | 71.675 | 1.177 | 87.442 | 0.43869 | 0.49378 | 0.51324 | 0.48875 | negative_slew_min, operating_region |

## Signed coordinates and independent predicates

The table keeps external ngspice-signed VGS/VDS and separately
type-oriented gate/drain voltages (NFET VGS/VDS; PFET VSG/VSD).
Internal model VTH and VDSAT are **not** substituted with external
terminal values. `on` means the frozen v2 internal VGS>VTH
and gm>0 predicate. `sat` is the separate internal VDSAT test.
All Id values below are raw internal model Id, in µA; the signed
supply-source current and stage voltages appear afterward.

| Corner | Role | Ext VGS / VDS V | Oriented gate / drain V | Model VTH / VDSAT V | On / headroom mV | Id µA | gm µS | gds µS | gm/abs(Id) V⁻¹ | on | sat |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| ss__high_v_low_t | input_minus | 0.71495 / 0.64089 | 0.71495 / 0.64089 | 0.71369 / 0.055423 | 1.2618 / 585.46 | 1.9367 | 44.512 | 0.30371 | 22.984 | True | True |
| ss__high_v_low_t | input_plus | 0.71495 / 0.64089 | 0.71495 / 0.64089 | 0.71369 / 0.055423 | 1.2618 / 585.46 | 1.9367 | 44.512 | 0.30371 | 22.984 | True | True |
| ss__high_v_low_t | load_first | -1.1541 / -1.1541 | 1.1541 / 1.1541 | 1.1612 / 0.058028 | -7.0972 / 1096 | 1.9367 | 40.485 | 0.069055 | 20.905 | False | True |
| ss__high_v_low_t | load_mirror | -1.1541 / -1.1541 | 1.1541 / 1.1541 | 1.1612 / 0.058028 | -7.0972 / 1096 | 1.9367 | 40.485 | 0.069055 | 20.905 | False | True |
| ss__high_v_low_t | second_load | -1.4205 / -1.438 | 1.4205 / 1.438 | 1.1059 / 0.29393 | 314.52 / 1144.1 | 116.79 | 657.42 | 11.294 | 5.6293 | True | True |
| ss__high_v_low_t | second_stage | 0.82593 / 0.54201 | 0.82593 / 0.54201 | 0.66762 / 0.13971 | 158.31 / 402.3 | 116.79 | 1275.6 | 13.578 | 10.923 | True | True |
| ss__high_v_low_t | tail | 0.72 / 0.18505 | 0.72 / 0.18505 | 0.66958 / 0.078274 | 50.415 / 106.77 | 3.8733 | 72.468 | 1.4332 | 18.71 | True | True |
| fs__nominal | input_minus | 0.70439 / 0.61918 | 0.70439 / 0.61918 | 0.66566 / 0.080115 | 38.732 / 539.06 | 2.97 | 54.958 | 0.35827 | 18.504 | True | True |
| fs__nominal | input_plus | 0.70439 / 0.61918 | 0.70439 / 0.61918 | 0.66566 / 0.080115 | 38.732 / 539.06 | 2.97 | 54.958 | 0.35827 | 18.504 | True | True |
| fs__nominal | load_first | -0.98521 / -0.98521 | 0.98521 / 0.98521 | 0.99543 / 0.076384 | -10.218 / 908.83 | 2.97 | 48.449 | 0.1091 | 16.313 | False | True |
| fs__nominal | load_mirror | -0.98521 / -0.98521 | 0.98521 / 0.98521 | 0.99543 / 0.076384 | -10.218 / 908.83 | 2.97 | 48.449 | 0.1091 | 16.313 | False | True |
| fs__nominal | second_load | -1.2405 / -0.7457 | 1.2405 / 0.7457 | 0.93002 / 0.30553 | 310.44 / 440.17 | 120.79 | 674.62 | 20.89 | 5.5851 | True | True |
| fs__nominal | second_stage | 0.81479 / 1.0543 | 0.81479 / 1.0543 | 0.60927 / 0.17633 | 205.52 / 877.97 | 120.79 | 1113.5 | 7.5822 | 9.2181 | True | True |
| fs__nominal | tail | 0.72 / 0.19561 | 0.72 / 0.19561 | 0.61825 / 0.11527 | 101.75 / 80.344 | 5.9399 | 83.991 | 2.6257 | 14.14 | True | True |
| fs__high_v_low_t | input_minus | 0.71602 / 0.72011 | 0.71602 / 0.72011 | 0.72221 / 0.052468 | -6.1933 / 667.64 | 1.6367 | 38.353 | 0.25903 | 23.433 | False | True |
| fs__high_v_low_t | input_plus | 0.71602 / 0.72011 | 0.71602 / 0.72011 | 0.72221 / 0.052468 | -6.1933 / 667.64 | 1.6367 | 38.353 | 0.25903 | 23.433 | False | True |
| fs__high_v_low_t | load_first | -1.0759 / -1.0759 | 1.0759 / 1.0759 | 1.1004 / 0.053715 | -24.466 / 1022.2 | 1.6367 | 34.874 | 0.06457 | 21.307 | False | True |
| fs__high_v_low_t | load_mirror | -1.0759 / -1.0759 | 1.0759 / 1.0759 | 1.1004 / 0.053715 | -24.466 / 1022.2 | 1.6367 | 34.874 | 0.06457 | 21.307 | False | True |
| fs__high_v_low_t | second_load | -1.4205 / -1.4862 | 1.4205 / 1.4862 | 1.0437 / 0.34868 | 376.74 / 1137.5 | 218.28 | 1020.2 | 22.986 | 4.6735 | True | True |
| fs__high_v_low_t | second_stage | 0.90409 / 0.49378 | 0.90409 / 0.49378 | 0.67585 / 0.18259 | 228.24 / 311.19 | 218.28 | 1693.4 | 29.274 | 7.7579 | True | True |
| fs__high_v_low_t | tail | 0.72 / 0.18398 | 0.72 / 0.18398 | 0.67789 / 0.073678 | 42.109 / 110.3 | 3.2735 | 63.646 | 1.1877 | 19.443 | True | True |

## Stage nodes and branch-current provenance

| Corner | Mirror V | Stage1 V | Tail V | Output V | Signed i(VDD) µA |
| --- | ---: | ---: | ---: | ---: | ---: |
| ss__high_v_low_t | 0.82593 | 0.82593 | 0.18505 | 0.54201 | -120.66 |
| fs__nominal | 0.81479 | 0.81479 | 0.19561 | 1.0543 | -126.73 |
| fs__high_v_low_t | 0.90409 | 0.90409 | 0.18398 | 0.49378 | -221.56 |

Signed `i(VDD)` is the independently observed supply-source
current. The seven model Id values are internal transistor
quantities, not independently sensed external branch currents; no
unverified branch-current equality is asserted. For interpretation,
the measured tail Id is approximately the sum of the two input
model Id values, and second-stage / second-load magnitudes are
close, but subcircuit parasitics limit a direct KCL proof.

## Diagnosis and scope

- `ss__high_v_low_t`: first-stage load pair misses the v2 on predicate;
  all frozen performance metrics pass.
- `fs__nominal`: first-stage load pair misses the v2 on predicate;
  all frozen performance metrics pass.
- `fs__high_v_low_t`: input pair and first-stage load pair miss
  the v2 on predicate; negative slew also misses its hard minimum
  (measured 0.48875 versus required 0.5 V/µs).

Thus device-on semantics is not the sole blocker in the third corner.
Every listed off-predicate device still has finite, nonzero Id
and gm in this measured candidate; `benchmark_on_condition_fail`
does **not** mean zero current or a physically dead stage.
This identifies constraint violations and plausible interacting
bias/size/headroom mechanisms for one design, not a unique causal
explanation of the whole 12-dimensional feasible region. Five-corner
sensitivity and bounded search provide further, still finite-budget
evidence. The v2 benchmark and hard specs remain unchanged.
