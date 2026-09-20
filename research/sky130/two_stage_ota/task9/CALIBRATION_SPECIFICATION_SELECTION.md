# Task 9 Calibration Specification Selection

The preregistered Sobol64 Full-PVT matrix produced zero robust-feasible
candidates at every one of the five preregistered ladder rows.  The target
0.1%--2.0% density band was therefore not achieved.  Per the frozen fallback,
all rows have the same distance (0.1 percentage point) to the closed band, and
the stricter lower-row tie break mechanically selects **row 0**
(`exact_task7_thresholds`).  No threshold was changed or interpolated.

Operating-region validity is invariant across the ladder; no calibration
candidate had all 15 corners operating-region valid (maximum four valid
corners for one candidate).  This explains why numerical relaxation did not
change robust density and is retained as a benchmark-difficulty limitation.

The selected specification hash is
`05b5c71863b852dc758cfed7643ace6aa9f6a7636856bf1eb09addef77681748`.  The calibration median complete
Full-PVT cost is 37.542 accumulated ngspice seconds, mechanically
selecting an equal-candidate budget of 20, equal-time budget of
375.415 seconds, candidate cap of 100,
and smoke budget of 10.

Exact per-row counts are in `calibration/ladder_evaluation.csv`; the complete
selection object and per-design selected-row robust violations are in
`calibration/selected_specification.json`.
