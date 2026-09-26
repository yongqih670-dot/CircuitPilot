# Frozen device-on and coordinate diagnostic protocol (Phase A)

No new ngspice run is performed in Phase A. Phase B, only after approval,
starts from the immutable best Task 9.5 12/15 in-bounds design in
`task9_5/feasibility/refinement_analysis.json` and its measured 45-analysis
matrix (SHA-256
`5bab8f3d1a792f5e374ee66f9264b3bb419d67f6533a18551adf1044e4be9ad7`).
The preidentified failed corners are `ss__high_v_low_t`, `fs__nominal`, and
`fs__high_v_low_t`; each is retained even if a fresh run varies slightly.
The frozen v2 benchmark hash is
`8f622a92370e33ea6f608d7a31077096b8188b868dc070cebbf3ce67f9059708`.

## Two voltage coordinate systems, both preserved

For every one of the seven roles, store external node voltages and terminal
differences with signs intact: `VGS_ext = VG−VS`, `VDS_ext = VD−VS`, and
`VBS_ext = VB−VS`. Also store the type-oriented external view: NFET
`VGS_n = VG−VS`, `VDS_n = VD−VS`; PFET `VSG_p = VS−VG`,
`VSD_p = VS−VD`. This is an algebraic sign conversion, **not** absolute
value erasure. Keep the original signed external fields alongside it.

The existing Task 9.5 model vectors `@m.xmN.m<device>[vgs/vds/vth/vdsat/gm/gds]`
are a third, distinct set: internal model operating-point quantities. The
locked SKY130 probe found positive type-oriented model VGS/VDS/VTH/VDSAT
for both NFET and PFET. External and internal voltages may differ because
the PDK subcircuit can contain parasitic elements; do **not** substitute
external `VSG_p` for internal model `vgs` in the benchmark predicate. Preserve
raw model VTH and VDSAT with source/units. The pure conversion is implemented
in `task9_6_device_coordinates.py` and tested for both transistor types.

The role-to-(drain, gate, source, bulk) mapping remains the frozen Task 7
`DEVICE_ROLE_MAPPING`. New diagnostic OP output must additionally capture
the `mirror` node (other stage/supply/bias nodes already exist), all seven
raw model `id` vectors, the original device vectors, supply current, stage1
node, tail node, output, and all external terminal nodes. New output files
go only into Task 9.6 run directories. First probe the `id` sign convention
and KCL consistency on a budgeted corner before interpreting direction;
do not modify the old netlist generator or imply a subcircuit internal Id
is automatically an independently sensed external branch current. Record
the measured branch-current source and status; mark unavailable if it cannot
be validated. Preserve raw signed Id even when a magnitude is also shown.

## Predicates and current efficiency

For each role/corner independently record:

- `benchmark_on_condition_pass`: internal model `vgs > vth` and positive
  measured gm under the frozen v2 rule;
- `model_saturation_condition_pass`: nonnegative internal VDS/VDSAT and
  `vds + 1e-6 V >= vdsat`, independently of on-condition;
- internal `vgs−vth`, `vds−vdsat`, signed/magnitude Id, gm, gds, external
  signed and type-oriented voltages, relevant branch current, stage nodes;
- `functional_stage_metrics_pass`: measured OP/AC/transient hard constraints
  per the unmodified Task 9 specification, including gain, UGF, PM, power,
  output, positive and negative slew; missing stage is `UNKNOWN`.

`gm_over_id = gm / abs(model_Id)` in inverse volts only if gm and Id are
finite, gm is nonnegative, and `abs(Id) > 1e-12 A`. At or below the frozen
floor, record ratio `null` and
`gm_over_id_status = "invalid_near_zero_current"`; absent Id is
`not_measured`. This ratio is descriptive and never replaces a hard
constraint. No zero-current interpretation follows from a failed
`vgs > vth` predicate: a device may carry meaningful current/gm near the
model threshold. Report the measured values and separate benchmark failure
from physical functional behavior.

The audit must answer, for all three failed corners and the seven roles,
which predicate fails; whether measured Id/gm are meaningful; whether the
VDSAT headroom test passes; which stage-level specs pass; and whether region
semantics is the sole or a combined blocker (the previous FS high-VDD/cold
matrix also missed negative slew). A single 12/15 design is evidence about
that design, not a causal explanation for the entire feasible region.
No v2 semantic or hard-spec change is authorized by this protocol.
