# Task 9 Nominal-to-PVT Robustness Gap Report

## Result

All **27** unique saved Task 7/8 nominal-feasible OTA designs were
evaluated with Full-PVT over all 15 frozen corners.  **0/27** remained
PVT feasible under specification-ladder row 0; therefore
**27/27** are nominal-feasible-but-PVT-failed.  This supports
pre-registered H5 and establishes the motivation for robust optimization.  It
does not select corners, train a predictor, or contribute observations to an
optimizer.

## Coverage and integrity

- Candidate sources: every saved evaluation table from Task 7 calibration,
  smoke, and formal plus Task 8 smoke, equal-candidate, and equal-time; identical
  parameter vectors were evaluated once and retain all source references.
- Complete work: 405 corner evaluations,
  405 OP, 405 AC,
  405 transient, and
  1215 real ngspice process calls.
- Analysis errors: 0.
- VDD checks: all measured OP supply values matched the requested corner.
- Temperature checks: all three ngspice logs per corner reported the requested
  temperature.
- Matrix SHA-256: `224c1cfcb9e172facadf116ae4461660adcd022e74e33e16473d219b6db5eab7`.

Full-PVT accumulated ngspice time per candidate was
36.625--38.483 s, with median
37.598 s and mean 37.499 s.
This observed cost may be used only by the already-required calibration protocol
to apply its pre-registered sample-size/budget rule.

## Most frequent failing corners

| Corner | Failed designs | Fraction |
|---|---:|---:|
| `fs__high_v_low_t` | 27/27 | 100.0% |
| `ss__high_v_low_t` | 27/27 | 100.0% |
| `sf__low_v_high_t` | 25/27 | 92.6% |
| `tt__high_v_low_t` | 25/27 | 92.6% |
| `ff__low_v_high_t` | 24/27 | 88.9% |
| `sf__high_v_low_t` | 24/27 | 88.9% |
| `ff__high_v_low_t` | 23/27 | 85.2% |
| `fs__nominal` | 23/27 | 85.2% |
| `fs__low_v_high_t` | 22/27 | 81.5% |
| `sf__nominal` | 22/27 | 81.5% |
| `ss__low_v_high_t` | 20/27 | 74.1% |
| `ss__nominal` | 20/27 | 74.1% |
| `tt__low_v_high_t` | 20/27 | 74.1% |
| `ff__nominal` | 11/27 | 40.7% |
| `tt__nominal` | 0/27 | 0.0% |


`tt__nominal` has zero failures, as expected from the source inclusion rule.
Every other count comes from a complete matrix, so order cannot censor these
frequencies.

## Constraint failures

Counts below are corner-design pairs and are multilabel; one pair can fail
several constraints.

| Constraint | Failed corner-design pairs | Fraction of 405 |
|---|---:|---:|
| `operating_region` | 284 | 70.1% |
| `output_low` | 92 | 22.7% |
| `negative_slew_min` | 45 | 11.1% |
| `phase_margin_min` | 35 | 8.6% |
| `positive_slew_min` | 33 | 8.1% |
| `ugf_min` | 23 | 5.7% |
| `gain_min` | 7 | 1.7% |
| `output_high` | 5 | 1.2% |
| `power_max` | 3 | 0.7% |


Operating-region failure is dominant.  This requirement is invariant across
all pre-registered specification-ladder rows, so numerical threshold relaxation
alone is not assumed to guarantee calibration feasibility.

## Reproducible evidence

- `candidate_set.json`: deduplicated nominal-feasible designs and provenance.
- `full_pvt_matrix.jsonl`: complete metrics, statuses, device evidence,
  constraint components, application checks, and costs.
- `corner_matrix.csv`: one flat row per design/corner.
- `design_summary.csv`: per-design robust outcome and taxonomy.
- `failure_by_corner.csv`, `failure_by_constraint.csv`, and
  `failure_by_corner_constraint.csv`: exact distributions.
- `failure_taxonomy.csv`: required multilabel taxonomy.
- `nominal_gap_summary.json`: counts, timing, hashes, and H5 decision.

Reproduce the matrix with `scripts/task9_full_pvt_research.py`, then regenerate
these summaries with `scripts/task9_analyze_nominal_gap.py`.
