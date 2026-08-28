# Task 5 Diagnostic Runs Excluded from Results

The following runs are infrastructure diagnostics only. They are excluded from
calibration density, smoke summaries, optimizer comparisons, KM/RMST, and the
formal baseline.

## cp-20260828T082029315667Z-6068ebf317dc

The first smoke attempt completed all three Random runs (25 candidates each)
and 14 candidates of DE seed 0 before the Python process terminated during
Matplotlib/Tk object cleanup on Windows. All 89 recorded candidate simulations
had process status success. The failure was outside ngspice and outside the
measurement/objective path.

The research plotting modules were changed to select the non-interactive Agg
backend before importing pyplot. No topology, device mapping, search space,
measurement, objective, constraint, benchmark hash, candidate budget, or
optimizer policy changed. The smoke suite is restarted from a new unique suite
directory; the partial run is never resumed or aggregated.
