# Task 4 Benchmark Difficulty Protocol

Protocol version: `task4_sky130_difficulty_v1`  
Status: pre-registered before any Task 4 calibration simulation.

The desired deterministic-grid feasible fraction is 1%–3%.  This is a
calibration difficulty target, not a promised optimizer success rate.  No
Random, DE, TPE, or BO observations may be used to select the specification.

The 256-point Cartesian calibration grid is declared in
`calibration_grid.yaml`.  The output-bias window is fixed at 0.30–1.50 V and
`operating_region_valid >= 1` is fixed before calibration.  The latter means,
using real MOS operating-point values, `VGS > VTH` and
`VDS >= VGS - VTH`.

Only these pre-registered threshold ladders may be considered:

- gain minimum (dB): 6, 8, 10, 12, 14, 16;
- bandwidth minimum (Hz): 1e8, 2e8, 5e8, 1e9, 2e9, 5e9;
- DC power maximum (W): 1e-4, 2e-4, 5e-4, 1e-3.

For every Cartesian combination, feasibility is computed using the frozen
right-censoring rule.  Select a combination within 1%–3% whose feasible
fraction is closest to 2%.  Ties are broken by higher gain threshold, then
higher bandwidth threshold, then lower power ceiling.  If no combination lies
inside the band, select the combination with at least one feasible point whose
fraction is closest to 2%, using the same tie break, and document the miss.

After selection, the specification and model/content hashes are frozen before
any optimizer smoke run.  The formal budget is pre-registered as 50; it may be
changed to 100 only before smoke if calibration yields no ladder combination in
the target band.  Once a formal run starts, the budget cannot change.

