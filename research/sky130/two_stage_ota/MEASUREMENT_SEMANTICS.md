# Task 7 Measurement Semantics

Status: frozen after implementation diagnostics and before calibration.

## Operating point

Version: task7_explicit_voltage_inequalities_all_seven_devices_v1

The OP analysis is an independent ngspice process at the frozen balanced
input. It records VDD current, power, stage1_out, vout, and for every M1--M7
role records VGS, VDS, VTH, gm, gds, and VDSAT.

An NMOS is valid iff VGS > VTH and VDS >= VGS - VTH. A PMOS is valid iff
abs(VGS) > abs(VTH) and abs(VDS) >= abs(VGS) - abs(VTH). Missing or
non-finite vectors, off devices, and triode devices have distinct recorded
labels. The candidate OP constraint is valid only when all seven devices are
in saturation.

## Open-loop AC, UGF, and phase margin

- AC testbench: task7_opposed_half_volt_unit_differential_v1
- UGF: task7_first_descending_zero_db_log_interpolation_v1
- phase margin: task7_unwrapped_phase_at_same_first_ugf_v1

The real AC process uses vin_plus = +0.5 and vin_minus = -0.5, hence one volt
differential excitation. ngspice vp() is converted from radians to degrees in
the netlist before parsing. Frequencies must be finite, positive, strictly
increasing; gain and phase must be finite; the low-frequency phase must be
within 90 degrees of the expected non-inverting polarity.

Phase is unwrapped before use. UGF is the first descending 0 dB crossing,
interpolated linearly in gain against log10 frequency. All descending
crossings are counted; multiple crossings are explicitly recorded while the
first remains the frozen selection. Phase margin is 180 + phase(UGF) using
the same interpolation fraction.

UGF statuses are measured, right_censored, no_crossing, invalid_response, and
analysis_error. A response still at or above 0 dB at f_stop is right-censored
with f_stop as a lower bound. Phase-margin statuses are measured, unavailable,
invalid_response, and analysis_error. The optional -3 dB bandwidth never
substitutes for UGF.

## Unity-follower transient and slew

- testbench: task7_unity_follower_fixed_0p8_1p0v_step_v1
- slew: task7_fixed_20_80pct_crossing_interpolation_v1

The independent transient process applies 0.8 V to 1.0 V at 0.5 us, returns
to 0.8 V at 2.0 us, ends at 4.0 us, and feeds vout to vin_minus. Rise/fall
time is 1 ns; maximum timestep is 2 ns. Crossing searches exclude the first
5 ns after each commanded edge. Positive slew is the fixed 0.84-to-0.96 V
output crossing slope; negative slew is the magnitude of the fixed
0.96-to-0.84 V output crossing slope. Both crossing times use linear
interpolation between transient samples. No maximum-derivative estimator is
used.

Each direction has status measured, insufficient_transition,
invalid_response, or analysis_error.

## Diagnostics that closed the freeze gate

The center diagnostic completed all three independent real SKY130 processes.
It produced a 3.129 MHz measured UGF and 81.95 degree phase margin after the
explicit radian-to-degree conversion. Both slew directions were measured.
Reducing maximum timestep from 2 ns to 1 ns changed positive slew by 0.067%
and negative slew by 1.45%, both below the pre-freeze 5% inflation tolerance.

## Full-only cost contract

Version: task7_full_three_independent_processes_v1

Every valid candidate attempts OP, AC, and transient even when an earlier
analysis or physical rule fails. The row records candidate count, process
count, each logical analysis count, high-fidelity count, per-analysis
runtime, candidate wall time, and cumulative totals. Screening cost is
identically zero and there is no Task 6 policy or hierarchy field.

