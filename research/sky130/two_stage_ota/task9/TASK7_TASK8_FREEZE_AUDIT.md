# Task 9 Freeze Audit for Tasks 7 and 8

Status: frozen before Task 9 PVT capability discovery or simulation.

Task 9 starts from Git commit
`fbe0d023555f715dd47fa4af6826316e10cdd3bf`. It may add PVT-specific
configuration and evaluation code, but it must not modify any Task 7 or Task 8
topology, search-space, PDK, nominal measurement, feasibility, raw-result, or
protocol identity.

## Frozen semantic identities

- Task 7 benchmark hash:
  `144100e168ca5f550c6ca0bd5a29788f669d0e34cd9008c5a7fe2099e8cb8c1c`
- Task 8 protocol hash:
  `d60ad33791a59bf418b0378e653e4e3bc10aa032dc98cde583d649260844dc2d`

## Frozen byte identities

| File | SHA-256 |
|---|---|
| `research/sky130/two_stage_ota/task7_frozen.yaml` | `077a42c053dfa59b6deb6e19dbca6cd74bec8122ebcb17998b906a4aa590df28` |
| `research/sky130/two_stage_ota/task7_protocol_manifest.json` | `edc0be16889aa111a4fc4d0845db0488820b1e00227bf19e9007f61c547da830` |
| `research/sky130/two_stage_ota/results/file_hashes.json` | `9d29f304849336d0db06f27fec285b483ce08d0ee1884465d795a9808bc90f78` |
| `research/sky130/two_stage_ota/TASK7_TWO_STAGE_OTA_REPORT.md` | `76af5cf58c524f69d793358ad20759c2c56e77ad3245cabe24cee70521f91b8f` |
| `research/sky130/two_stage_ota/task8/task8_protocol_manifest.json` | `9ca7caf490338683aad3d5ef6f50d87427130e9c3b95c8e3f227d44dc070d053` |
| `research/sky130/two_stage_ota/task8/file_hashes.json` | `d7c362cded7ac3f08def2d56d85b0f2d4746a07660155e271fd893f6f16a7e59` |
| `research/sky130/two_stage_ota/task8/TASK8_HIERARCHICAL_EVALUATION_REPORT.md` | `16918114e0e15d9bf2f37438bc7965f4f17c57384dbaea70868ddac5c823f597` |
| `research/sky130/two_stage_ota/task8/results/task8_summary.json` | `6bb6321e0d6d1d753f549a11405b168d04bc2b5bd825e13a08ee1a53e936edf5` |
| `src/circuitpilot/task7_protocol.py` | `cbfc6ae45a3a259bdb4f29de18c245e419d94c949e6e795d318b60031ab82960` |
| `src/circuitpilot/task8_protocol.py` | `863a11fbae6178d0c3b48be981ea12a7890a0dbe81ce7d4604c3644a6535d98a` |

Task 9 tests must recompute every identity in this table. A mismatch is a hard
failure and prohibits calibration, optimizer experiments, and publication.
