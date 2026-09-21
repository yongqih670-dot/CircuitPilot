# Related PVT-Aware Analog Sizing and Evaluation Methods

Literature review cutoff: 2026-09-21. This positioning was written after the
Task 9 protocol and formal experiments and therefore did not select corners,
thresholds, ordering, budgets, or hypotheses.

## Established context

PVT-constrained analog sizing predates this work. Lourenço, Martins, and Horta
present a systematic treatment of automatic analog sizing constrained by PVT
corners and layout effects in their 2017 monograph
([Springer, DOI 10.1007/978-3-319-42037-0](https://doi.org/10.1007/978-3-319-42037-0)).
Task 9 therefore makes no claim that evaluating or optimizing analog circuits
over PVT corners is new.

Recent learning-based work explicitly targets the cost of variation-aware
sizing:

- **RobustAnalog** treats variations as related optimization tasks and prunes
  the task space during multi-task reinforcement learning
  ([MLCAD 2022, DOI 10.1145/3551901.3556487](https://doi.org/10.1145/3551901.3556487);
  [open manuscript](https://arxiv.org/abs/2207.06412)).
- **PVT-Transfer** transfers knowledge among corner-specific sizing tasks and
  uses selective simulation in a multi-task evolutionary framework
  ([IEEE TCAS-I 2024, DOI 10.1109/TCSI.2023.3340683](https://doi.org/10.1109/TCSI.2023.3340683)).
- **PVTSizing** combines trust-region Bayesian optimization and reinforcement
  learning for batch-sampled PVT-robust synthesis
  ([DAC 2024, DOI 10.1145/3649329.3661850](https://doi.org/10.1145/3649329.3661850);
  [author manuscript](https://yibolin.com/publications/papers/ANALOG_DAC2024_Kong.pdf)).
- **PPAAS** uses goal-conditioned reinforcement learning and includes a
  skip-on-fail simulation strategy to reduce PVT simulation overhead
  ([ICCAD 2025 manuscript](https://arxiv.org/abs/2507.17003);
  [open implementation](https://github.com/SeunggeunKimkr/PPAAS)).
- **GLOVA** extends variation-aware learning to global/local mismatch and
  proposes simulation reordering for lower verification cost
  ([2025 manuscript](https://arxiv.org/abs/2505.11208)). This is broader than
  Task 9, which intentionally excludes mismatch Monte Carlo.
- **HR²** applies hierarchical multi-agent reinforcement learning and
  lightweight variation modeling to robust sizing across PVT conditions
  ([MLCAD 2025, DOI 10.1109/MLCAD65511.2025.11189231](https://doi.org/10.1109/MLCAD65511.2025.11189231)).
- **PASO** uses progressive nominal-to-worst-corner Bayesian optimization and
  explicitly includes corner pruning
  ([Microelectronics Journal 2026, DOI 10.1016/j.mejo.2026.107186](https://doi.org/10.1016/j.mejo.2026.107186)).

These works establish that PVT-aware sizing, knowledge transfer, progressive
corner inclusion, simulation reordering, skip-on-fail evaluation, and corner
pruning already exist. Task 9 does **not** claim first PVT corner pruning, first
progressive PVT optimization, or superiority to those methods; it did not run
their code under a common benchmark.

## Task 9's narrower role

Task 9 establishes an auditable deterministic baseline with a different
contract:

1. real open SKY130A TT/SS/FF/FS/SF models and a frozen 15-corner suite;
2. exact logical-AND PVT feasibility, with no averaging across corners;
3. OP → AC → transient gating within a corner and static worst-first gating
   across corners;
4. early rejection only after a real completed measurement proves a frozen
   hard-constraint violation—never from a learned predictor, surrogate,
   parameter heuristic, or adaptive per-candidate order;
5. null physical metrics for every unrun stage or corner;
6. offline replay plus shadow-Full audits for exact feasibility preservation;
7. process-level elapsed-time accounting, checkpoint/resume, and budget checks
   immediately after each completed ngspice analysis; and
8. paired Random/DE/TPE/BO experiments with six-axis KM/RMST and deterministic
   bootstrap analysis.

This contract is deliberately conservative. It gives future learned or agentic
methods a reproducible baseline to exceed without silently changing the
benchmark, weakening robustness, or accepting false feasibility.

## Boundary of the comparison

Task 9 covers one two-stage OTA topology, one open PDK/model tree, 15 discrete
PVT corners, and deterministic sizing. It does not address mismatch yield,
layout parasitics, topology generation, dynamic search spaces, adaptive corner
prediction, or learned cross-corner transfer. Those omissions prevent broad
state-of-the-art claims and motivate the next research stage.
