# Frozen Operating-Point Physics Rules

Status: pre-registered before implementation and pilot execution.

Version: task6_op_physics_rules_v1

Only real per-candidate DC operating-point values are used. For an NMOS,
overdrive is VGS minus VTH and drain headroom is VDS. For a PMOS, overdrive is
the absolute value of VGS minus the absolute value of VTH, and drain headroom
is the absolute value of VDS.

A device is off when overdrive is less than or equal to zero. An on device is
not saturated when drain headroom is less than overdrive. Equality in the
saturation condition is valid, matching the frozen Task 5 rule.

The primary violation types and mask bits are:

| Bit | Value | Type | Trigger |
|---:|---:|---|---|
| 0 | 1 | input_pair_off | either input NMOS is off |
| 1 | 2 | input_pair_not_saturated | either on input NMOS is not saturated |
| 2 | 4 | active_load_off | either PMOS load is off |
| 3 | 8 | active_load_not_saturated | either on PMOS load is not saturated |
| 4 | 16 | tail_off | the tail NMOS is off |
| 5 | 32 | tail_not_saturated | the on tail NMOS is not saturated |
| 6 | 64 | output_headroom_invalid | VOUT is outside the inclusive Task 5 interval 0.25-1.55 V |

The mask is the bitwise union of all simultaneous triggers. The violation
count is the number of triggered primary types, not the number of devices.
multiple_physics_violations is a derived label added when the count exceeds
one; it has no independent mask bit.

physics_status is valid only when the mask is zero. Otherwise it is invalid
and the Screened policy rejects the candidate before AC. Device-region
validity remains the original Task 5 all-five-device Boolean; output headroom
remains a separate Task 5 constraint. Missing or non-finite OP evidence is an
analysis error, not a physics rejection.

