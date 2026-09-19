# Task 8 Evaluation Policy

Status: pre-registered before replay, implementation, or new simulation.

Version: task8_op_ac_transient_safe_hierarchy_v1

## Shared feasibility identity

Both policies use Task 7 benchmark
144100e168ca5f550c6ca0bd5a29788f669d0e34cd9008c5a7fe2099e8cb8c1c
and its unchanged nine hard-constraint components. Task 8 never predicts a
metric and never changes what constitutes a feasible OTA.

## Full policy

Full reproduces the Task 7 evaluator exactly. Every candidate attempts one
OP, one open-loop AC, and one unity-follower transient analysis in independent
ngspice processes. It uses the original Task 7 objective and feasibility
calculation without a Task 8 gate.

## Hierarchical policy

### Stage 1: OP

Run the frozen balanced-input OP analysis. Continue only if every OP-dependent
hard constraint passes:

- all seven devices satisfy operating_region_valid;
- dc_power_w is at most 1.5 mW; and
- output_dc_voltage is inside 0.10–1.70 V inclusive.

The deterministic first-blocker priority is operating_region, power, then
output_bias. A measured failure ends the candidate as op_rejected. Gain, UGF,
phase margin, and both slew metrics remain null. AC and transient are not run.

An OP process, parse, or measurement error is an analysis failure, not a safe
physics/specification rejection.

### Stage 2: AC

Run the frozen open-loop AC analysis only after Stage 1 passes. Continue only
if:

- dc_gain_db is at least 12 dB;
- UGF has a constraint-valid exact or bounded value at least 0.5 MHz; and
- phase margin is measured at the frozen valid crossing and is at least 35
  degrees.

The deterministic first-blocker priority is gain, UGF, then phase_margin.
No-crossing, invalid-response, or analysis-error UGF cannot satisfy the UGF
and PM pair. A right-censored UGF lower bound may satisfy UGF, but because
Task 7 phase margin is unavailable without its selected exact crossing, it
still stops at phase_margin. A measured failure ends as ac_rejected and both
slew metrics remain null. Transient is not run.

An AC process or parse error is an analysis failure, not a safe rejection.

### Stage 3: transient

Run the frozen unity-follower transient only after OP and AC pass. Apply the
unchanged Task 7 objective to all collected measurements. A positive or
negative slew failure ends as transient_rejected; a fully feasible result
ends as fully_feasible. The first-blocker priority is positive_slew then
negative_slew.

## Terminal stages

Hierarchical terminal stages are op_rejected, ac_rejected,
transient_rejected, and fully_feasible. Full terminal stages are
full_infeasible and fully_feasible. Transient-executed is also recorded as a
nonexclusive cost counter for stage-distribution reporting.

Measured hard-constraint failure is not simulation_failed. No optimizer may
branch on the subtype of a rejection beyond receiving the frozen scalar
feedback described in PARTIAL_FEEDBACK_SEMANTICS.md.

## Replay and shadow gates

Offline replay applies these rules to all frozen Task 7 rows without invoking
ngspice. Smoke Hierarchical runs execute only missing analyses after a
rejection as a shadow audit. Shadow measurements never reach the optimizer
and their calls and elapsed time are stored in separate audit-cost fields.
