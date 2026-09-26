# Evidence archive manifest

The Git history still contains the frozen Task 6--9 reports, indexes, hashes,
formal tables and selected raw evidence. The 907 previously tracked research
files are checked by `history_freeze.json` and its regression test. The
following complete *formal-run raw source roots* additionally have independent
local ZIP archives. These are not Git-tracked or uploaded; there is currently
no public download URL. Their storage base is:

`F:\芯片设计\CircuitPilot：Agentic Circuit Simulation and Optimization Platform\research_runs\task9_5_archives\`

| Task | ZIP file | ZIP bytes | ZIP SHA-256 | Source files | Source bytes | Git-tracked / local-only files in archive |
| --- | --- | ---: | --- | ---: | ---: | ---: |
| 6 | `task6_raw_evidence.zip` | 225,384,396 | `6a156f4f93e89f9e6f7378b0f762980953eb003f2ce86315a9069184e41447bb` | 128,133 | 729,099,511 | 0 / 128,133 |
| 7 | `task7_raw_evidence.zip` | 63,449,086 | `28910eb97693cd75d5ea2eb5a0917739a64414f98551ae66eb197f9fbb8a2d39` | 23,502 | 327,947,166 | 78 / 23,424 |
| 8 | `task8_raw_evidence.zip` | 175,086,257 | `869314b1a40a2a529ca1dfd8484d957698e2df40a97fe95de1c95b5228b426d4` | 87,613 | 819,678,821 | 472 / 87,141 |
| 9 | `task9_raw_evidence.zip` | 625,141,424 | `6bae52f2a013b1ce7fb9b616c0766893bc627b34a3c8ced573ea180d8e18d89b` | 238,149 | 3,531,572,234 | 25 / 238,124 |

All four archives were generated against associated Git commit
`d6bfddb9b33a340b212f456ba7941fcc1614b18e` using
`C:\Anaconda\python.exe scripts/task9_5_archive_evidence.py task6` (replace
`task6` with `task7`, `task8`, or `task9`). The generation script stores
repository-relative paths and fixed ZIP timestamps. Each ZIP's SHA-256 and
the source roots/counts are also in its adjacent, local-only
`taskN_archive_manifest.json`.
All four archives passed a complete `zipfile.ZipFile.testzip()` CRC readback
(returned `None` for each archive).

Archived source roots:

- Task 6: `research_runs/task6/`, `research_runs/task6_postfix/`.
- Task 7: `research_runs/task7/`, `research/sky130/two_stage_ota/results/`.
- Task 8: `research/sky130/two_stage_ota/task8/results/`.
- Task 9: `research/sky130/two_stage_ota/task9/results/`.

Git separately tracks 24 Task 6 formal/smoke raw-evidence ZIPs under
`research/sky130/differential_amplifier/task6/results/raw_evidence/`. The
Task 7 tracked results include selected raw evidence, not its complete run
tree. Task 8 and Task 9 `results/*/runs/` trees are ignored by `.gitignore`;
the Task 6/7 `research_runs/` trees and these new independent archives are
also ignored. Nonformal probes and temporary development runs outside the
listed roots are not represented as complete formal evidence.

Reproducibility scope: a Git-only checkout can reproduce the audited code,
summary tables, historical hashes and selected/Task-6 archived raw evidence,
but cannot replay every Task 7--9 simulator response. Full raw replay
requires the four local ZIPs (or an independently hosted byte-identical copy),
the locked SKY130 PDK/model tree, ngspice environment and documented runner.
The user should copy the ZIPs to durable independent storage before relying
on this workstation as the sole raw-evidence archive. No historical file was
deleted or rewritten during this audit.
