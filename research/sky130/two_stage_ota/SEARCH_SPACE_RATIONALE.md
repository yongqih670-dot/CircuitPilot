# Task 7 Search-Space Design Prior

Status: pre-registered before implementation, simulation, or calibration.

Version: task7_role_matched_12d_prior_v1

Task 7 uses 12 variables. Matched devices share role-level geometry, and the
fixed tail-bias voltage removes a thirteenth dimension while retaining an
independent second-stage current-control variable.

| Variable | Physical role and matching | Lower | Upper | Unit | Sampling | Expected qualitative influence |
|---|---|---:|---:|---|---|---|
| input_pair_width_m | Shared M1/M2 width | 0.84e-6 | 30e-6 | m | log | Input gm, noise, first-stage current split, capacitance, UGF |
| input_pair_length_m | Shared M1/M2 length | 0.15e-6 | 1.0e-6 | m | linear | Output resistance, gain, headroom, speed |
| first_stage_load_width_m | Shared M3/M4 width | 0.84e-6 | 40e-6 | m | log | Mirror current density, first-stage gain, parasitic capacitance |
| first_stage_load_length_m | Shared M3/M4 length | 0.15e-6 | 1.2e-6 | m | linear | Mirror output resistance, gain, pole location |
| tail_width_m | M5 width | 0.42e-6 | 30e-6 | m | log | Tail current capability, input-pair gm, power, slew |
| tail_length_m | M5 length | 0.15e-6 | 1.2e-6 | m | linear | Tail output resistance, common source-node stiffness, headroom |
| second_stage_width_m | M6 width | 0.84e-6 | 60e-6 | m | log | Second-stage gm, gain, drive, nondominant pole, power |
| second_stage_length_m | M6 length | 0.15e-6 | 1.2e-6 | m | linear | Second-stage output resistance, gain, speed |
| second_load_width_m | M7 width | 0.84e-6 | 60e-6 | m | log | Output bias current, source/sink asymmetry, drive, power |
| second_load_length_m | M7 length | 0.15e-6 | 1.2e-6 | m | linear | Load output resistance, gain, output pole |
| second_load_bias_v | M7 explicit gate bias | 0.25 | 1.20 | V | linear | Second-stage bias current, output DC point, power, slew |
| compensation_capacitance_f | Miller Cc between stage1_out and vout | 0.05e-12 | 5.0e-12 | F | log | Dominant-pole splitting, UGF, phase margin, slew |

Width and compensation ranges use log sampling because useful behavior spans
orders of magnitude. Length and voltage ranges use linear sampling. Bounds
are based only on SKY130 1.8 V device geometry and standard two-stage OTA
trade-offs; no Task 7 optimizer or calibration result was consulted.

## Fixed conditions outside the search

The 1.8 V supply, 0.9 V input common mode, 1.0 pF load, 27 C temperature, and
0.72 V tail bias are frozen topology/testbench conditions rather than search
variables. The 12-dimensional cap is intentional: independently sizing every
matched transistor would add nonphysical degrees of freedom, while tying
first- and second-stage load geometry would conflate distinct current-density
and pole-placement roles.

