# Task 7 Two-Stage Miller OTA Topology Protocol

Status: pre-registered before implementation, simulation, or calibration.

Version: sky130_two_stage_miller_ota_v1

## Selected canonical topology

Task 7 uses a seven-MOS, single-ended, two-stage Miller-compensated OTA. This
is the standard extension of the frozen five-transistor differential stage:
an NMOS common-source second stage and a PMOS current-source load are added,
with a Miller capacitor from the first-stage output to the final output.

The topology is selected because it exposes the intended gain, nondominant
pole, phase-margin, compensation, drive, power, and slew trade-offs without
introducing cascodes, common-mode feedback, rail-to-rail inputs, or topology
selection. It will not be changed after calibration or optimizer results.

## Device and node mapping

The external signal convention makes vin_plus the non-inverting OTA input and
vin_minus the inverting input after both gain stages.

| Role | Primitive | D / G / S / B | Shared size role |
|---|---|---|---|
| input_minus_m1 | sky130_fd_pr__nfet_01v8 | mirror / vin_minus / tail / gnd | input_pair |
| input_plus_m2 | sky130_fd_pr__nfet_01v8 | stage1_out / vin_plus / tail / gnd | input_pair |
| first_load_diode_m3 | sky130_fd_pr__pfet_01v8 | mirror / mirror / vdd / vdd | first_stage_load |
| first_load_output_m4 | sky130_fd_pr__pfet_01v8 | stage1_out / mirror / vdd / vdd | first_stage_load |
| tail_source_m5 | sky130_fd_pr__nfet_01v8 | tail / tail_bias / gnd / gnd | tail_source |
| second_stage_m6 | sky130_fd_pr__nfet_01v8 | vout / stage1_out / gnd / gnd | second_stage_device |
| second_load_m7 | sky130_fd_pr__pfet_01v8 | vout / second_load_bias / vdd / vdd | second_stage_load |

All four MOS terminals are explicit. There is no implicit bulk, synthetic
model, fallback device, or reference N1 device.

## Compensation, load, and bias

- Miller compensation capacitor Cc connects stage1_out to vout.
- Load capacitor CL connects vout to ground and is fixed at 1.0 pF.
- VDD is fixed at 1.8 V.
- Input common-mode voltage is fixed at 0.9 V.
- Temperature is fixed at 27 C.
- The tail gate uses an explicit ideal 0.72 V DC bias.
- The second-stage PMOS load uses an explicit ideal DC bias whose voltage is a
  design variable.

The ideal bias voltages isolate transistor sizing and compensation behavior;
Task 7 does not claim a self-biased production OTA.

## Required testbench copies

Each candidate receives three independent real SKY130 analyses:

1. Balanced-input operating point at vin_plus = vin_minus = 0.9 V.
2. Differential open-loop AC with +0.5 V phasor at vin_plus and -0.5 V
   phasor at vin_minus, producing a unit differential input.
3. Unity-gain negative-feedback transient with the command applied to
   vin_plus and vout fed back to vin_minus.

No CMRR testbench is included. No candidate may skip an analysis in Task 7.

