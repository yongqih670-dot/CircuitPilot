# Task 5 Search-Space Rationale

Status: frozen before calibration under task5_sky130_differential_difficulty_v1.

| Variable | Range | Sampling | Matching | Physical role and expected influence |
|---|---:|---|---|---|
| input_pair_width_m | 0.84-10 um | log | M1=M2 | Input transconductance, input capacitance, gain and bandwidth |
| input_pair_length_m | 0.15-0.80 um | linear | M1=M2 | Output resistance, intrinsic gain and speed |
| active_load_width_m | 0.84-20 um | log | PMOS mirror pair 1:1 | Mirror current density, output resistance, capacitance and bias |
| active_load_length_m | 0.15-1.00 um | linear | PMOS mirror pair 1:1 | Mirror output resistance, gain, matching prior and speed |
| tail_width_m | 0.42-12 um | log | one tail role | Tail current capability, common-mode rejection and power |
| tail_length_m | 0.15-1.00 um | linear | one tail role | Tail output resistance, CMRR, headroom and speed |
| tail_bias_v | 0.55-1.00 V | linear | shared by both testbench copies | Tail current, headroom, power and operating-region validity |

All device dimensions stay inside the documented 01v8 primitive limits used by
Task 4. Seven role variables prevent premature dimensional explosion while
guaranteeing symmetry through the design-variable mapping rather than optimizer
coincidence. These are circuit-design priors, not explanations fitted to
calibration or optimizer results.

