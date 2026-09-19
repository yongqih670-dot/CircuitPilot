# Task 8 Frozen Protocol

Status: frozen after replay and cost profiling, before evaluator implementation.

- Task 8 protocol hash: d60ad33791a59bf418b0378e653e4e3bc10aa032dc98cde583d649260844dc2d
- frozen source commit: 67607dac935e61c53b106580bc769845581195ae
- Task 7 benchmark hash: 144100e168ca5f550c6ca0bd5a29788f669d0e34cd9008c5a7fe2099e8cb8c1c
- replay candidates: 2000
- replay false rejections: 0
- methods: Random, DE, TPE, BO
- policies: Full, Hierarchical
- formal seeds: 0–9
- equal-candidate budget: 50
- equal-time budget: 90.0 accumulated ngspice seconds
- equal-time candidate cap: 300

## Frozen semantic hashes

| Component | SHA-256 |
|---|---|
| Full evaluation policy | d9c51eed6c92a8c2b5ea849d9ef237bda0357c320bdcd2480eb0030624b5f532 |
| Hierarchical evaluation policy | ff9f9e0301143bdb6b82974911e6dae1e35490ef209e326c8f1453d8558c757d |
| evaluation stages | c32c752c254f4d5aac457b4be6e4eab019885ea6789a8e329b21f758025305b7 |
| partial feedback | c8b3589596b37acdac1cba753b25a1e494f922c4f0794a435a12ec2ab53e919d |
| simulation-time budget | b4e01972b75320835ca94e7b465a8f5a5c3a6ad08053dbd2fb685b5423b148ea |
| cost accounting | 857dd2d286c6f2dcaed584b7da02fc33342bf5fb01b52c383f76cdc27a816d0e |

The byte identities of every preregistration document, replay output, cost
profile summary/table, and pure policy implementation are stored in
task8_protocol_manifest.json. Formal execution must abort if any identity
changes.
