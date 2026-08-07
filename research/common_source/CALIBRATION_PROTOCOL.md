# Common-Source Calibration Protocol

Status: declared before the first calibration run.

The Task 3 calibration is a deterministic Cartesian grid over the four frozen
candidate dimensions. It is not an optimizer run and consumes no Random, DE,
TPE, or BO seed. Parameter order and values are stored in
`calibration_grid.yaml`; the grid SHA-256 and every real ngspice call are stored
in the calibration manifest.

Rules:

1. Run the grid once, with one combined `.op` + `.ac` ngspice process per grid
   point.
2. Preserve each point's netlist, ngspice log, raw AC output, raw DC operating
   point, optional MOS operating-point output, timing, status, and error evidence.
3. Calibration data determines a physically plausible search space and
   specification of moderate difficulty only. It is never included in optimizer
   summaries, plots, seed sets, or algorithm comparisons.
4. Select and document the specification from the completed raw distributions;
   then freeze `common_source_frozen.yaml` and its benchmark hash before smoke
   validation.
5. After freeze, feasibility may be annotated onto the existing raw calibration
   rows without any new simulation. No calibration point is rerun or hidden.
6. Any later change to topology, model bytes, fixed values, search space,
   analysis, metrics, objective, constraint, or success criterion creates a new
   benchmark hash and invalidates all prior baseline runs.

The initial deterministic grid has 81 points: three widths, three lengths,
three drain resistances, and three input biases. It spans the declared search
space without tuning for any optimizer.
