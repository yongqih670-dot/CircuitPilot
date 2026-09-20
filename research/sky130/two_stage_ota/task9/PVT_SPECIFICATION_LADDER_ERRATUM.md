# Task 9 Specification-Ladder Serialization Erratum

Before any ladder-row evaluation, corner-order derivation, replay, policy
implementation, smoke, or optimizer experiment, PyYAML 6.0.2 was found to load
the preregistered positive-exponent spellings such as `5.0e5` as strings.

The spellings were changed to YAML numeric equivalents such as `5.0e+5`.
There is no numerical or semantic change to any threshold, ladder row, target
density, or selection rule.  The completed Full-PVT calibration collected raw
metrics/statuses only and did not use a ladder row, so it is unaffected.  Git
history preserves both the preregistered source and this representation-only
correction.  Row evaluation begins only after this correction is committed.
