# Task 9.5 Operating-Region Semantics Audit

## Historical meaning and proposed v2

The frozen Task 7--9 operating-region test is hereby named
`long_channel_proxy_v1`.  It checks `VGS > VTH` and `VDS >= VGS - VTH` for
NMOS, with absolute magnitudes for PMOS.  It is an explicit long-channel
voltage proxy.  It is not a simulator `region` enum, and prior wording that
suggested a model-defined region must be read with this correction.  The
historical implementation, datasets, and hashes are not changed.

The audited counterfactual `model_consistent_saturation_v2` retains a
conservative on rule, `VGS > VTH`, and requires positive measured `GM` and
nonnegative `GDS`.  For an on device it checks `VDS + 1e-6 V >= VDSAT`, with
finite values and nonnegative model-reported `VDSAT`.  Reverse `VDS` is
invalid.  Missing or non-finite evidence is invalid.  The 1 microvolt headroom
tolerance is a numerical equality allowance, not a deliberate physical margin.
Equality at `VDSAT - 1e-6 V` passes; a smaller `VDS` fails.  Off devices fail
the hard region requirement under both semantics.

The [ngspice manual](https://ngspice.sourceforge.io/docs/ngspice-manual.pdf)
labels MOS operating-point `vdsat` as saturation voltage and `vds` as
drain-source voltage.  Unlike the elementary overdrive approximation, this
quantity comes from the active compact model.  `VDS >= VDSAT` is still a
chosen benchmark criterion, not a claim that ngspice returned a categorical
region label or that transistor current becomes exactly voltage-independent.

## Real-model sign and current evidence

`scripts/task9_5_probe_vdsat.py` independently ran 15 fresh ngspice OP probes
over the frozen 5 process x 3 voltage/temperature suite.  Each saved probe
contains a netlist, raw output, and simulator log in `region/probe/`, and
`region/probe_summary.json` records all seven quantities and raw SHA-256.
The test circuits place an NMOS and PMOS in normal on states.  Every probe
reported positive internal `vgs`, `vds`, `vth`, `vdsat`, `id`, `gm`, and `gds`
for both device types.  At TT/1.8 V/27 C, the PMOS reported `vgs=0.9 V`,
`vds=1.8 V`, `vth=0.5100 V`, `vdsat=0.3482 V`, and `id=21.71 uA` in the
ngspice subcircuit's internal type-normalized coordinates.  These are not the
external PMOS gate-source/drain-source signed node differences.  The v2
classifier therefore uses measured internal positive coordinates for both
types and does not take `abs(vds)`: 32 negative PMOS `vds` values in the
Task 9 Formal A evidence are reverse-voltage cases, not valid positive
headroom.

The Task 7--9 OP evidence saved `vgs`, `vds`, `vth`, `vdsat`, `gm`, and `gds`,
but not per-device `id`.  The fresh probes verify the current sign and that
`id` is available from this model.  Historical offline replay can only use
the six saved quantities; it cannot retroactively assert an `id` threshold.
Consequently v2 keeps the explicit `VGS > VTH` on criterion, supplemented by
positive `GM`.  A later benchmark could preregister and capture `id` for every
candidate if a current-based on rule is desired.

## Complete historical classification replay

The audit replayed every saved Task 7--9 OP evidence record available in the
tracked calibration, smoke, and formal tables, plus the Task 9 nominal-gap
and Sobol matrices.  It first recomputed v1 and required exact agreement with
the saved per-role status before applying v2.  The verification passed.
`region/device_classification_transitions.csv` breaks down results by
benchmark, design, optimizer method, policy, corner, and device role.

| Per-device transition | Count |
|---|---:|
| valid under both | 149,656 |
| invalid under both | 126,068 |
| v1 valid, v2 invalid | 1,228 |
| v1 invalid, v2 valid | 997 |

The tail device accounts for the largest shift in Task 9: 350 cases changed
from valid to invalid and 530 from invalid to valid.  These comparisons are
record-level, not independent silicon samples; the same parameter vector can
appear in paired policies and across corners.

## Counterfactual feasibility and screening impact

Among 1,915 distinct nominal candidate parameter vectors with sufficient
saved full measurements, 27 were v1 feasible and 24 v2 feasible.  Three
historical nominal positives were demoted; none was promoted.  Task 9's
nominal-gap set remains 0/27 PVT feasible under v2, and independent Sobol64
calibration remains 0/64.  Formal A remains 0/800 PVT feasible.  Strict
Formal B has 346 completed Full-PVT matrices, also 0 PVT feasible under both
versions.  Partial budget-terminal matrices are excluded.

The unchanged zero counts do not mean the hard criterion is unchanged.
In Formal A's 12,000 complete corner assessments, 33 corner region outcomes
switch from valid to invalid and 12 from invalid to valid.  Region-invalid
corner counts change from 11,862 to 11,883.  The nominal-gap set changes from
284 to 299 region-invalid corners, and Sobol64 from 945 to 947.  Offline
static-worst-first replay over complete Full matrices changes the first
measured rejection point for 2 nominal-gap candidates, 1 Sobol calibration
candidate, and 1 Formal A candidate.  Formal B and smoke first points did not
change.  See `region/full_matrix_counterfactual.csv` and
`region/region_replay_summary.json` for each complete design.

For live Hierarchical-PVT candidates, some v1 OP rejections would no longer
be justified by the region criterion under v2.  Their later AC, transient, and
corner measurements were never made, so historical partial records cannot
prove a v2 final outcome.  The complete Full matrices quantify the changed
rejection points without inventing those missing measurements.

## Semantics identity and decision implication

- v1 semantics hash:
  `f01ae3c760525b5740e0acb1a42bd2427baa503b7c22bc7ba8a636bc0e4bcf80`
- v2 semantics hash:
  `87507210656ff3f4e23fbb42852b80194be4b82c3e2ebb36e06e176685cd53e1`

The hashes bind the on rule, headroom rule, PMOS sign convention, and numerical
tolerance.  Unit tests verify classification and hash sensitivity.  Because
v2 changes real hard-feasibility decisions and safe rejection points, a future
Task 10 comparison using v2 requires a new benchmark hash.  The frozen Task 9
benchmark cannot silently acquire v2 semantics.
