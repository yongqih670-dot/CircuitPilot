# Task 8 Task 7 Freeze Audit

Status: recorded before Task 8 replay, implementation, or simulation.

Task 8 changes only the evaluation policy. The Task 7 topology, role mapping,
PDK, search space, hard constraints, objective, measurements, cost evidence,
and raw results are immutable.

## Frozen identity

| Item | SHA-256 |
|---|---|
| Task 7 Git commit | f3419d8f44e3f0c923f7f7671f716dbb2a847dc2 |
| benchmark_config_hash | 144100e168ca5f550c6ca0bd5a29788f669d0e34cd9008c5a7fe2099e8cb8c1c |
| task7_frozen.yaml bytes | 077a42c053dfa59b6deb6e19dbca6cd74bec8122ebcb17998b906a4aa590df28 |
| task7_protocol_manifest.json bytes | edc0be16889aa111a4fc4d0845db0488820b1e00227bf19e9007f61c547da830 |
| results/file_hashes.json bytes | 9d29f304849336d0db06f27fec285b483ce08d0ee1884465d795a9808bc90f78 |
| TASK7_TWO_STAGE_OTA_REPORT.md bytes | 76af5cf58c524f69d793358ad20759c2c56e77ad3245cabe24cee70521f91b8f |
| calibration.csv bytes | 27d0603b460005c9fe9e89a584a2850548bd7c8fb31a9917aa09994bf45883ef |

## Frozen implementation bytes

| File | SHA-256 |
|---|---|
| src/circuitpilot/sky130_two_stage_ota.py | 8d7036df107854d1cc0c33d3841f705454e4df91527695f18b9cd32730a9db7d |
| src/circuitpilot/task7_protocol.py | cbfc6ae45a3a259bdb4f29de18c245e419d94c949e6e795d318b60031ab82960 |
| src/circuitpilot/experiments/task7_runner.py | b72f139f6dd8aa45f2de56329240bc70e5a48fed4b09065b911816ead9af359f |
| src/circuitpilot/experiments/task7_recorder.py | f70c84c805c65ae4dc8a5cb9e6927c9b7cba3ad51540b0a76f35d65850d5ad51 |
| src/circuitpilot/experiments/task7_batch.py | bcc0fcf100d6cefd532d9629e4f4fce32a29ceb4c853bf8c70e0c72d2f36a974 |
| scripts/finalize_task7.py | 1519285555642ae76225091500f9c0e491a5ee3ee2f42dc80524b2b96a97b6a6 |

Task 8 tests recompute these values. Any mismatch stops Task 8. No Task 8
artifact may be written beneath the frozen Task 7 results directory.
