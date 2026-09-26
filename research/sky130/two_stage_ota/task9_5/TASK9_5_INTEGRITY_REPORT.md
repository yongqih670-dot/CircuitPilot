# Research Task 9.5 — benchmark-integrity final report

Task 9.5 is an additive audit of frozen Tasks 6--9, not a new optimizer
comparison. No historical raw data, reports, formal conclusions or benchmark
hashes were overwritten. The pre-audit freeze covers 907 Git-tracked files;
their byte-level SHA-256 inventory is
`f14c6a31818ba69a3e3d08b1344de56fcc95f0ca090d367e0d55dca3b6a9f196`.

## Findings

1. **Statistics.** A supported common restriction horizon is now required
   for group Kaplan--Meier/RMST comparisons. Of 420 recalculated rows,
   48 historical RMST values change (28 Task 6, 20 Task 8); Tasks 7 and 9
   values do not. Task 6 pooled formal equal-AC Full RMST changes from
   119.850 at unsupported 200 AC to 76.100 at supported 92 AC; screened
   remains 34.742. Task 8 pooled equal-time RMST remains 88.602 vs 79.150
   at 90.797 s; Task 9 remains 113.471 vs 113.471 with no PVT successes.
   H2 and H3 remain supported; H4 remains unsupported. Task 6 per-analysis
   simulator-time RMST is unreconstructible from frozen records and is not
   invented. See [statistics addendum](STATISTICS_CORRECTION_REPORT.md).
2. **Device physics.** The historical criterion is explicitly
   `long_channel_proxy_v1`, not model-defined saturation. A fresh 15-corner
   SKY130/ngspice OP probe checked normalized PFET/NFET signs, VTH, VDSAT,
   ID, GM and GDS. The additive `model_consistent_saturation_v2` requires an
   on device and `VDS + 1 µV >= model VDSAT`; reverse VDS is not made positive
   by an absolute value. Offline replay reproduced v1 before counterfactual
   v2 classification. Across 1915 distinct nominal measured candidates,
   feasible count changes 27 to 24; three positives are demoted. Task 9
   complete Full-PVT sets remain zero feasible, but corner hard outcomes and
   four static first-rejection points change. Consequently the old Task 9
   hash cannot silently be reused. See [semantics audit](OPERATING_REGION_SEMANTICS_AUDIT.md).
3. **Stability.** Of 28,247 saved raw AC responses, none of the 17,344 valid
   measured-UGF responses had more than one unity crossing. The 882 raw
   two-crossing responses began below unity and were correctly invalid under
   historical UGF semantics. No critical descending PM is worse than first
   PM; no hard feasibility or Task 9 PVT outcome changes. PM semantics can
   stay at v1. Missing waveforms for 1365 preformal Task 9 corners are an
   explicit coverage limit. See [crossing audit](MULTIPLE_CROSSING_AUDIT.md).
4. **Corrected benchmark identity.** A semantics-only Benchmark v2 was frozen
   before search at hash
   `8f622a92370e33ea6f608d7a31077096b8188b868dc070cebbf3ce67f9059708`,
   distinct from Task 9's
   `ec2d4de0e0c5694598cc7444b4fa9b63a8d8b533fa68bdd504e5262ebd5e2d61`.
   It keeps the same 12-D bounds, fixed bias, 15 corners, hard specs and
   first-crossing PM. See [v2 manifest](benchmark_v2_manifest.json).
5. **Feasibility.** Pre-registered, fully logged in-bounds diagnosis made
   437 attempts, including 105 fresh complete 15-corner OP evaluations.
   Best reached 12/15 OP-pass corners. Fresh complete 45-analysis negative
   characterization independently confirmed 12/15 all-constraint-pass
   corners and correct VDD/temperature application. Three SS/FS corners
   failed mainly because first-stage mirror/load or input devices were off;
   one of those also missed negative slew by 2.25%. Gain, UGF, PM, power,
   output and positive slew passed all 15 in that design. A separate
   out-of-benchmark fixed-tail-bias sweep gave no simple improvement.
   Feasible-set emptiness is **not** proven. No witness document or real
   positive-screening validation is claimed. See [diagnosis](ROBUST_FEASIBILITY_DIAGNOSIS.md).
6. **Evidence and claims.** Independent local, SHA-256-recorded and CRC-read
   ZIPs preserve complete formal raw roots for Tasks 6--9 and Task 9.5
   diagnostics. Search ledgers and the complete negative matrix are also
   losslessly compressed in Git. ZIPs are local-only, not publicly
   downloadable; Git alone cannot replay every Task 7--9 raw response. See
   [archive manifest](EVIDENCE_ARCHIVE_MANIFEST.md). Current BO is a
   lightweight baseline, not state-of-the-art constrained BO. Synthetic
   positive-path tests and negative-only replay do not replace a real
   positive safe-screening experiment.

## Decision and verification

[Decision C](DECISION_FOR_TASK10.md): **Task 10 formal Agent research must
not start.** V2 semantics are mandatory for any corrected continuation, but
Benchmark v2 is not yet proven solvable. No hard spec or search-space change
is adopted. A genuine 15-corner, 45-analysis positive witness and empirical
Hierarchical-PVT positive/boundary validation remain prerequisites.

Regression coverage includes RMST supported horizons, vdsat parsing and
NFET/PFET semantics, historical replay, semantics-hash sensitivity,
crossing/critical-PM logic, Full-PVT verifier and synthetic hierarchical
positive path, frozen Task 6--9 byte hashes, and v2 hash separation. The
complete suite passed **345 tests, 1 skipped** (Task 3 requires an unset
`SKY130_MODEL_LIBRARY` environment variable) using a no-whitespace pytest
temporary directory. All four historical archives and the Task 9.5 archives
passed ZIP CRC readback. The best diagnostic Full matrix made all 45 fresh
ngspice calls with no application-check failure.
