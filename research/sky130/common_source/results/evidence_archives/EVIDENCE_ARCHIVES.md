# Task 4 Evidence Archives

These ZIP files preserve complete accepted run directories, including every
candidate netlist, ngspice log, raw AC data, raw DC operating-point data, raw
MOS operating-point data, canonical CSV/SQLite records, optimizer state,
configuration, environment manifest, plots, and summaries.

| Workflow | Run ID | Size (bytes) | ZIP SHA-256 |
|---|---|---:|---|
| calibration | `cp-20260807T110401181924Z-9987aa0da32f` | 1,217,644 | `058eaa8d9638fcc43a30e48e1ba6a21f134369f4639d6b7939ae6152c480facc` |
| accepted smoke | `cp-20260807T111655257288Z-cbeae67e02e6` | 3,376,459 | `8f1361a3c0e9392f1b438cd54905279b9ecb340dd90a15be77e758db088718b9` |
| accepted formal baseline | `cp-20260807T112328876830Z-afedfa321406` | 17,044,088 | `42a137f02df0deb894632ab60962631ca6125998cccf2191746ba493bff1486a` |

The installed PDK itself is intentionally not duplicated in these archives.
Its provenance, release/commit, 840-file content hash, and top-library hash are
stored in every manifest and frozen YAML.
