# Task 9 PVT Model Capability Report

## Scope and decision

This audit was completed before the Task 9 corner suite, hypotheses, calibration,
or optimizer experiments were frozen.  It does not modify any Task 7 or Task 8
file.  The installed SKY130A/Open_PDKs model tree contains real `tt`, `ss`, `ff`,
`fs`, and `sf` MOS process fragments for both
`sky130_fd_pr__nfet_01v8` and `sky130_fd_pr__pfet_01v8`.  All five process
corners executed successfully in ngspice at each of the three proposed voltage
and temperature conditions (15 independent operating-point probes).

The audited Task 9 execution envelope is **1.62 V through 1.98 V** and **-40 C
through 125 C**.  This statement means that the content-locked models and the
real simulator successfully execute this frozen research envelope; it is not a
foundry reliability or lifetime qualification claim.  Task 9 keeps the Task 7
topology, devices, and nominal measurement semantics, while a new Task 9 PVT
configuration will carry non-nominal supply, temperature, and process choices.
The intentionally TT-only Task 7 configuration remains frozen.

## Provenance and identity

- Distribution: FOSSi Foundation Ciel/Open_PDKs prebuilt SKY130A
- PDK release: `1.0.606`
- Open_PDKs commit: `026824c7969ce6f4fc9678e6ca04b0a06a596c4b`
- `sky130_fd_pr` primitive commit: `403964dc7f9cca5ec1a8cc7b4f2a6f532b781676`
- Top-level library SHA-256: `17c208a699228f5acb87bf59c09c22a4c4d3937b6766b4957737d34e8e075f64`
- Complete ngspice + primitive model-tree SHA-256: `d88fa42b4f42f7b1f6987141aa92161865cfc9ff5fbdce9bbc9f137bde3a2f61`
- Model-tree file count: `840`
- Simulator: repository-local `ngspice_con.exe`; every probe exited with status 0

The machine-readable manifest records the absolute library location, resolved
simulator, section inventory, model identities, and every probe result in
`capability/capability_audit.json`.  Per-fragment SHA-256 values are retained in
`capability/capability_probes.csv`.

## Discovered `.lib` sections

The actual top-level library was parsed; section names were not inferred.  The
following 51 sections were found:

```text
tt sf ff ss fs ll hh hl lh
sf_ll sf_hh sf_hl sf_lh
ff_ll ff_hh ff_hl ff_lh
ss_ll ss_hh ss_hl ss_lh
fs_ll fs_hh fs_hl fs_lh
tt_mm sf_mm ff_mm ss_mm fs_mm ll_mm hh_mm hl_mm lh_mm
sf_ll_mm sf_hh_mm sf_hl_mm sf_lh_mm
ff_ll_mm ff_hh_mm ff_hl_mm ff_lh_mm
ss_ll_mm ss_hh_mm ss_hl_mm ss_lh_mm
fs_ll_mm fs_hh_mm fs_hl_mm fs_lh_mm
mc
```

Interpretation:

- `tt`, `ss`, `ff`, `fs`, and `sf` are the five real MOS process choices
  relevant to the Task 7 OTA and were directly verified using the corresponding
  NFET and PFET primitive fragments.
- `ll`, `hh`, `hl`, and `lh` describe non-MOS interconnect/passive combinations;
  combined sections such as `ss_hh` combine MOS and passive selections.  The
  Task 7 OTA uses ideal compensation and load capacitors and contains no modeled
  resistors or extracted interconnect, so these sections do not add a distinct
  active-device process condition for this benchmark.
- Every `*_mm` section and `mc` activates mismatch or Monte Carlo behavior and is
  excluded because Task 9 explicitly forbids mismatch Monte Carlo.
- No missing section was aliased or synthesized.

## Real execution verification

Each probe copied the content-locked invariant file and the selected NFET/PFET
`corner.spice` and `pm3.spice` files to an ASCII temporary directory, selected
the process through those real fragments, injected `.temp`, applied an explicit
`VDD` source, and ran a real ngspice `.op`.  The retained log contains ngspice's
reported `TEMP`; the retained output contains the measured `v(vdd)`.  The audit
fails if either differs from its request.

| V/T condition | Requested VDD | Requested temperature | Process fragments tested | Result |
|---|---:|---:|---|---|
| nominal | 1.80 V | 27 C | TT, SS, FF, FS, SF | 5/5 passed |
| low-V/high-T | 1.62 V | 125 C | TT, SS, FF, FS, SF | 5/5 passed |
| high-V/low-T | 1.98 V | -40 C | TT, SS, FF, FS, SF | 5/5 passed |

All 15 measured VDD values equal the requested values within `1e-9 V`, and all
15 ngspice-reported temperatures equal the requested temperatures within
`1e-9 C`.  Process switching also changed measured primitive characteristics;
for example, at 1.80 V/27 C the NFET threshold was 0.769267561 V (TT),
0.816512267 V (SS), 0.717931665 V (FF), 0.835861163 V (FS), and
0.695863671 V (SF).  This provides a direct check that five different model
fragments, rather than labels on one model, were active.

## Evidence and reproduction

- Driver: `scripts/task9_pvt_capability_audit.py`
- Machine-readable manifest: `capability/capability_audit.json`
- Flat results and primitive hashes: `capability/capability_probes.csv`
- Immutable raw netlist/output/log for each probe: `capability/raw/<corner_id>/`

Run from the repository root:

```powershell
C:\Anaconda\python.exe scripts/task9_pvt_capability_audit.py
```

The audit result supports pre-registering the five MOS process corners crossed
with the three verified voltage/temperature conditions.  Whether all five are
included is decided in the corner protocol before calibration and optimizer
results, as required.
