# Task 5 Freeze Audit for Research Task 6

Status: recorded before Task 6 implementation or pilot execution.

Task 6 reuses the immutable Task 5 circuit benchmark. It adds an evaluation
policy experiment only and does not change circuit feasibility.

| Evidence | SHA-256 |
|---|---|
| Task 5 benchmark configuration hash | 57d2183621ecf37e5ca22e012452c43fce6459be7d347a5cfc93d0b394c14378 |
| differential_amplifier_frozen.yaml bytes | bdcfd6f38367a48a5d16583deb5a02495ca8b3938afbc1b2df1707ba75421f38 |
| calibration.csv bytes | 4e7c09ddf84271be3b4d75003f8873d88664a7c814256770479a046f9aa9f18b |
| formal baseline_results.csv bytes | 0078a6015316eeec15c8bc8994a1b39fcb2a236d56ec6abad33f7bdbbc187c34 |
| formal baseline_summary.csv bytes | 63b813f49db3ed248932e95fd3ceed50cf846e7881b4c003443cd814e7417707 |
| formal raw-evidence archive bytes | f9c31ef42f374de7332bbbbc65e272460fc0e553849e7865fa14ef442dd39883 |

The Task 5 evidence publication commit is
59e880236777c0238f101b090cb7ecd5706d3857. Task 6 tests must recompute the
benchmark hash and check these byte hashes. Files outside the new task6
subdirectory are read-only for this research task.

