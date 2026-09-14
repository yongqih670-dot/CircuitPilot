# OP-Only Feedback Semantics

Status: pre-registered before implementation and pilot execution.

Version: task6_normalized_op_violation_feedback_v1

An OP-rejected candidate has a successful simulator process, physics_status
invalid, and evaluation_stage op_rejected. Differential gain, common-mode
gain, bandwidth, bandwidth lower bound, CMRR, and CMRR lower bound remain
explicitly null. No theoretical AC proxy is computed.

For each of the five devices, define overdrive and drain headroom according to
PHYSICS_RULES.md. The device violation is:

1. off deficit = max(0, 1e-9 V minus overdrive) divided by
   max(abs(VTH), 1e-3 V);
2. saturation deficit = zero for an off device, otherwise
   max(0, overdrive minus drain headroom) divided by
   max(overdrive, 1e-3 V);
3. device violation = off deficit plus saturation deficit.

The output violation is the sum of the distance below 0.25 V and the distance
above 1.55 V, divided by the 1.30 V valid-window width. The recorded
op_constraint_violation is the mean of the five device violations and the
output violation. Any physics-invalid candidate therefore has a positive
value.

The optimizer-facing objective for a rejected candidate is:

1000 + op_constraint_violation / (1 + op_constraint_violation).

It lies in [1000, 1001). An OP-valid, full-evaluated candidate retains the
exact Task 5 ObjectiveEvaluator result. The experiment aborts if a real
full-evaluation objective is not below 1000, so every accepted OP-rejected
candidate is ordered after every OP-valid full-evaluated candidate without
rescaling Task 5 feedback.

For a rejected record, the common constraint_violation column contains the
OP-only violation for optimizer audit and is_feasible is always false. For a
full-evaluated record, constraint_violation and is_feasible retain exact Task 5
meaning. Feasibility is never inferred from the OP-only objective.

