# Task 7 Prior-Research Freeze Audit

Status: recorded before Task 7 topology implementation or calibration.

Task 7 is an independent benchmark. It does not modify, reinterpret, or use
optimizer results from Tasks 5 or 6 to choose its topology, search space,
measurement semantics, or specifications.

## Frozen identities

| Artifact | Frozen identity |
|---|---|
| Task 5 benchmark_config_hash | 57d2183621ecf37e5ca22e012452c43fce6459be7d347a5cfc93d0b394c14378 |
| Task 5 frozen YAML byte SHA-256 | bdcfd6f38367a48a5d16583deb5a02495ca8b3938afbc1b2df1707ba75421f38 |
| Task 6 policy-family hash | 53b1eb73160b4d069135f406613cd1249fcdd002bfd6cb2b0c8892da1c3b4867 |
| Task 6 Full policy hash | a07ea20ee7f16598602fa7f05218b45439e4bb87ac34c786d9881125372de0f0 |
| Task 6 OP-Screened policy hash | 28110a5127748f185c35f038b2a4dcf333356ae54e676391042cebeff0cfe065 |
| Task 6 physics-rule hash | 704634265dcbc3e0e8a7dd56eb4bd07c385bf26b0ad4ce0f306bdc43401ce052 |
| Task 6 feedback-semantics hash | 2890448082b38377353526406abcd78cdca7b23f86d8a6765bbfb9f26bce3d27 |
| Task 6 cost-model hash | 1ddf380b35fa8f5628c10e1f6e25cf87a32ef336a4ce0f306bdc43401ce052 |
| Task 6 frozen YAML byte SHA-256 | 9e6e720575f729fd4014a465c1123786e3cbf63472377cda9b6864cc332288d4 |
| Task 6 publication hash-index byte SHA-256 | 17e195aaf7223b55bdbc04bd23999f717f340c0838911bd315243ddb9191e5a8 |
| Task 6 report byte SHA-256 | 2247530d2583c83e2aa8350fd41508e6e0b53edc4274b435a516c1ea6a4a662f |

Task 7 tests must recompute these byte hashes and the Task 5 benchmark hash.
Task 5 raw evidence and every Task 6 result remain read-only. Task 6 wall-time
results retain their published interpretation.

## Scope boundary

Task 7 contains only a Full evaluator. It may reuse general infrastructure
such as optimizer interfaces, run identities, model verification, survival
statistics, and the isolated Windows SKY130 runtime, but it must not import or
activate Task 6 OP screening, staged policy feedback, or Task 6 observations.

