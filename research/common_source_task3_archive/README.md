# Research Task 3 immutable archive

Status: permanently frozen from the research perspective.

Research Task 3 is the ngspice-reference-BSIM3 common-source benchmark. Its
configuration, measurements, failures, raw outputs, and conclusions must not be
rewritten in light of Research Task 4. Task 4 is a separate SKY130 benchmark
with a new benchmark hash and a different bandwidth-measurement semantics.

## Frozen identifiers

- benchmark configuration SHA-256:
  `d60664b436ce9a928da2db86ca83378d556f18ddcf54b633394609f67288bec9`
- semantic freeze commit:
  `51ac2714df4c5fc8661ec0fedd06c3447e4c21e9`
- clean commit recorded by the locked baseline runs:
  `7bae910f599b6e9402427c5983a05ca52b58f8aa`
- model: ngspice 46 reference BSIM3 `N1` (explicitly not SKY130)
- model SHA-256:
  `e14792f8adbe569d6f4152292343bc9fb0a41364a5aa1a5ad476b82f70316168`

## Authoritative locations

- frozen definition: `research/common_source/common_source_frozen.yaml`
- benchmark documentation: `research/common_source/COMMON_SOURCE_BENCHMARK.md`
- calibration: `research/common_source/common_source_calibration.csv`
- final report: `research/common_source/TASK3_COMMON_SOURCE_REPORT.md`
- tracked baseline tables: `research/common_source/results/baseline/`
- complete raw-run archives:
  `research/common_source/results/evidence_archives/`
- original locked baseline run:
  `research_runs/task3_common_source_baseline/cp-20260807T083800448980Z-5be94980f0c1`

## Frozen file checksums

| File | SHA-256 |
| --- | --- |
| `common_source_frozen.yaml` | `abc502cd2b67d2df466b3715f40baced399613886299c5eda868493ef0c42299` |
| `COMMON_SOURCE_BENCHMARK.md` | `0735845fdbb8c3cd88a6adca3f939797873e4b81d899310a72aafb488bb153da` |
| `common_source_calibration.csv` | `3ecac58407a6c7af15fc3a174f208c7898bc32e696c8a0ac74ecb43eda9fda7b` |
| `TASK3_COMMON_SOURCE_REPORT.md` | `96c4439323da284c46379364bcacda33e7486d218e020c3c7d20b27bb848ac3d` |
| `results/baseline/baseline_results.csv` | `25d94202a56efcf28a1b24f9e5e72b828e71ced86267e14995a73d233fb0b67b` |
| `results/baseline/baseline_summary.csv` | `e207c35d74e22215410d7144afcbb44bd1eff49b7d123aff113d1a681b470a13` |
| `results/baseline/fairness_validation.json` | `9e8d56ff1806ce35717664e0fb15a9bed027fbe44683333e32511b646437e0ad` |
| `ngspice_bsim3_nmos.lib` | `e14792f8adbe569d6f4152292343bc9fb0a41364a5aa1a5ad476b82f70316168` |

## Known limitations and no-crossing semantics

Task 3 used a fixed 10 Hz to 1 GHz AC window. A valid response with no
post-peak -3 dB crossing before 1 GHz raised `AnalysisError` and was recorded as
`analysis_failed`. The locked formal baseline therefore contains 427 such
records. These records are not ngspice process failures, but this distinction
was not represented by the Task 3 evaluation schema.

Research Task 4 introduces explicit right-censoring for new SKY130 runs only.
It is forbidden to relabel Task 3's 427 `analysis_failed` records, impute a
bandwidth, recompute its tables, or apply the Task 4 estimator retroactively.

## Immutability rule

Any future correction to a Task 3 artifact must be issued as a new benchmark
and new hash. The files and results listed here remain historical evidence and
must be treated as read-only by calibration, optimization, statistics, and
report-generation code.
