# Task 4 Diagnostic Runs Excluded from Results

Two pre-formal infrastructure diagnostics are retained locally under
`research_runs/` but are excluded from all accepted tables and plots.

1. `cp-20260807T111104955534Z-c51e624c16bb` was the first smoke attempt.  It
   exposed a floating-point endpoint defect: DE decoded the exact upper width
   bound as `7.000000000000002e-6`, so five candidate slots were rejected before
   ngspice.  The common unit-cube decoder now clamps decoded values to the
   declared physical interval; regression coverage was added.  Accepted smoke
   was rerun from a clean commit with 300/300 real ngspice calls.
2. `cp-20260807T112008930008Z-cc23e4541d9b` was the first formal attempt.  The
   nested unique IDs exceeded the traditional Windows path-length limit.  It
   stopped after the first 50-slot run, all before ngspice, and the suite refused
   to create results because no netlist existed.  Compact artifact names plus
   short mapped I/O paths fixed this; a real 235+-character-path SKY130 test was
   added.  Accepted formal was restarted in a new unique directory.

Neither diagnostic contributes candidate data, success rates, KM estimates,
or optimizer comparisons in the Task 4 report.
