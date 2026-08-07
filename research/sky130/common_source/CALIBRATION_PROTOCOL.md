# Task 4 SKY130 Calibration Protocol

Status: declared before the first Task 4 calibration run.

Calibration is a deterministic 4×4×4×4 Cartesian grid (256 candidates), not
an optimizer.  Parameter order and values are stored in
`calibration_grid.yaml`.  Each point receives exactly one real ngspice process
containing `.op` and the same fixed `.ac` sweep.

Every point preserves its generated netlist, ngspice log, raw DC data, raw MOS
operating-point data, raw AC data, status, timing, and error evidence.  Exact
bandwidth and right-censored bandwidth are kept distinct.  The calibration CSV
may be annotated with the frozen specification without rerunning any point.

Calibration may be used only to validate the search space, inspect physical
metric distributions, confirm a nonempty feasible region, and apply the
pre-registered threshold-selection rule.  It cannot be used for algorithm
comparison, optimizer tuning, or per-method search-space changes.

