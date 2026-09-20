# Task 9 PVT Corner Protocol

Status: pre-registered after the model-capability audit and before nominal-gap,
calibration, replay, implementation, smoke, or optimizer experiments.

Version: `task9_five_process_three_vt_full_factorial_v1`

## Scope

Task 9 uses a finite, explicit robustness suite; it does not claim coverage of
all manufacturing or field conditions.  The suite preserves the frozen Task 7
OTA topology, search space, primitive devices, testbenches, measurement
semantics, and constraint meanings.  A Task 9 corner changes only the real MOS
process fragments, supply voltage, and temperature listed below.

## Fixed inclusion rule

Include every non-mismatch MOS process choice for which this installation has
both real `sky130_fd_pr__nfet_01v8` and `sky130_fd_pr__pfet_01v8`
`corner.spice` plus `pm3.spice` fragments.  The capability audit establishes
that the resulting set is exactly `tt`, `ss`, `ff`, `fs`, and `sf`.

The asymmetric FS and SF corners are included because the OTA contains both
NFET and PFET signal-path devices and both asymmetric combinations are real.
They cannot be removed after observing feasibility or optimizer behavior.
Passive-only `ll/hh/hl/lh` selections do not alter the ideal Task 7
capacitors and there are no modeled resistors or extracted interconnect, so
they are not separate active-device corners here.  All mismatch and Monte
Carlo sections (`*_mm`, `mc`) are excluded by Task 9 scope.  No missing or
excluded corner may be aliased, synthesized, or estimated.

## Fixed voltage/temperature conditions

| Condition ID | VDD | Temperature | Purpose |
|---|---:|---:|---|
| `nominal` | 1.80 V | 27 C | frozen nominal electrical condition |
| `low_v_high_t` | 1.62 V | 125 C | combined low-supply/high-temperature stress |
| `high_v_low_t` | 1.98 V | -40 C | combined high-supply/low-temperature stress |

All three conditions were executed successfully for all five process choices
before this protocol was written.  The 1.98 V point is an audited simulation
condition, not a device-reliability qualification statement.

## Frozen 15-corner suite

The suite is the full Cartesian product of the five process choices and three
V/T conditions.  `corner_id` is `<process>__<condition>`.

| Suite index | corner_id | Process | VDD | Temperature |
|---:|---|---|---:|---:|
| 0 | `tt__nominal` | TT | 1.80 V | 27 C |
| 1 | `tt__low_v_high_t` | TT | 1.62 V | 125 C |
| 2 | `tt__high_v_low_t` | TT | 1.98 V | -40 C |
| 3 | `ss__nominal` | SS | 1.80 V | 27 C |
| 4 | `ss__low_v_high_t` | SS | 1.62 V | 125 C |
| 5 | `ss__high_v_low_t` | SS | 1.98 V | -40 C |
| 6 | `ff__nominal` | FF | 1.80 V | 27 C |
| 7 | `ff__low_v_high_t` | FF | 1.62 V | 125 C |
| 8 | `ff__high_v_low_t` | FF | 1.98 V | -40 C |
| 9 | `fs__nominal` | FS | 1.80 V | 27 C |
| 10 | `fs__low_v_high_t` | FS | 1.62 V | 125 C |
| 11 | `fs__high_v_low_t` | FS | 1.98 V | -40 C |
| 12 | `sf__nominal` | SF | 1.80 V | 27 C |
| 13 | `sf__low_v_high_t` | SF | 1.62 V | 125 C |
| 14 | `sf__high_v_low_t` | SF | 1.98 V | -40 C |

The table order is the canonical corner-suite order used in hashes and Full-PVT
matrices.  It is not a claim that later entries are more or less difficult.

## Feasibility and objective

A candidate is PVT feasible if and only if every one of the 15 corners has all
required measurements/statuses valid and satisfies every hard constraint in
the mechanically selected frozen specification-ladder row.  This is a logical
AND, never an average.  One measured corner failure proves PVT infeasibility.

For each scalar constraint `i` and corner `c`, normalized violation is:

- lower bound: `max(0, (threshold - value) / max(abs(threshold), 1e-30))`;
- upper bound: `max(0, (value - threshold) / max(abs(threshold), 1e-30))`;
- operating region: `0` for valid and `1` for invalid; and
- missing, non-finite, or constraint-invalid required measurement/status: `1`.

The robust violation is `sum_i max_c violation(i,c)`.  PVT feasibility requires
robust violation exactly zero plus all required measurement statuses valid.
Among feasible candidates the frozen secondary objective is minimum
worst-corner DC power, `max_c dc_power_w`.  This objective will not change after
results are observed.

## Corner-level and worst-corner evidence

Every started corner stores `corner_id`, process, VDD, temperature, gain, UGF,
phase margin, power, output DC, positive/negative slew, operating-region result,
and every underlying measurement/status field.  Unrun physical metrics are
null, never predicted or copied.

For a complete matrix, report minima for gain, UGF, phase margin, both slews,
and output margin; report the maximum for power.  Each summary stores its own
`worst_corner_for_<metric>`.  There is no universal worst corner.

## Fixed nominal-first descriptive order

The descriptive `NOMINAL_FIRST_ORDER` is:

```text
tt__nominal, ss__nominal, ff__nominal, fs__nominal, sf__nominal,
tt__low_v_high_t, ss__low_v_high_t, ff__low_v_high_t,
fs__low_v_high_t, sf__low_v_high_t,
tt__high_v_low_t, ss__high_v_low_t, ff__high_v_low_t,
fs__high_v_low_t, sf__high_v_low_t
```

Formal Hierarchical-PVT experiments will instead use one static worst-first
order derived from independent Sobol calibration by the pre-registered rule in
`PVT_CALIBRATION_PROTOCOL.md`.  Once derived, that order is identical for every
candidate, method, policy comparison, and seed.

