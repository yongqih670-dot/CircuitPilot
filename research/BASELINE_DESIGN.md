# CircuitPilot Traditional Optimization Baseline Design

## 统一执行架构

```text
ExperimentConfig -> Optimizer.ask() -> ExperimentRunner -> RC Simulator -> ngspice
                         ^                                      |
                         |                                      v
                   Optimizer.tell() <- ObjectiveEvaluator <- Analyzer
                                                |
                                      CSV + SQLite + manifest
```

Random、DE、TPE 和 BO 只实现同一个 `Optimizer` 接口。它们不能导入 Simulator、读取 ngspice 文件或自行计算电路指标。`ExperimentRunner.run_to_budget()` 是唯一候选执行循环；方法选择只发生在循环外的工厂中。

成功 trial 的 `bandwidth` 来自真实 ngspice AC 输出及 −3 dB 插值。失败 trial 的 `raw_metrics`、`objective_value` 和 `constraint_violation` 为空，不使用 penalty 或理论截止频率代替仿真结果。

## 固定 RC baseline

- 电路：已审计的 `rc_lowpass`。
- 搜索空间：R = 100–100000 Ω（log-float），C = 1e-10–1e-5 F（log-float）。
- 目标：`bandwidth = 10000 Hz`。
- 标量目标：`abs(simulated_fc - 10000) / 10000`，统一最小化。
- 成功判据：relative error ≤ 0.05 且约束违反为 0。
- AC 分析：0.01 Hz–100 MHz，每 decade 40 点。
- PVT：空配置；Task 2 不实现 PVT variation。

四个 YAML 中除 method、实验显示名称、输出根目录和 optimizer-specific hyperparameters 外，上述条件完全相同。`FairnessValidator` 在合并前再次核验这些条件。

## Random Search

- 实现：CircuitPilot 内部实现；数值采样使用 NumPy Generator。
- 支持：float、int、categorical、log-scaled float。
- 超参数：无。
- seed：只使用 `ExperimentConfig.seed` 初始化的统一 `SeedContext`。
- ask/tell：`ask` 在声明顺序中逐维采样；有 pending candidate 时禁止再次 ask；每个 ask 必须配对 tell。
- failure：仅保存失败状态，不改变采样分布。
- resume：JSON 保存 NumPy bit-generator state、pending candidate 和全部反馈。
- 限制：不利用历史反馈，是有意保留的无模型控制组。

## Differential Evolution

- 实现：CircuitPilot 内部的标准 generation-based ask/tell 状态机，数值运算使用 NumPy。
- 选择理由：SciPy 高层 `differential_evolution()` 会在一次调用内隐藏多次 objective invocation，不满足逐候选预算审计；内部状态机保持标准 DE 变异/二项交叉语义，并让每次候选都经过共同 Runner。
- 默认超参数：`population_size=8`、`mutation=0.8`、`recombination=0.7`、`strategy=best1bin`；也支持 `rand1bin`。
- seed：统一 NumPy Generator。
- ask/tell：初始化种群的每个成员逐个 ask/tell；一代开始时冻结上一代，逐 target 产生 trial，并在 tell 时进行选择。
- budget：初始化候选和 trial 都各消耗一次预算；可在未完成一代时立即停止。
- failure：失败候选没有 fitness。失败 trial 不替换 target；失败的初始化成员保留为无 fitness 成员，后续成功 trial 可替换它。没有伪造 fitness。
- resume：JSON 保存 RNG、population、fitness、generation snapshot、target index 和历史，可从半代继续。
- 限制：Task 2 仅支持连续 float 空间和两种 binomial strategy。

## Optuna TPE

- 实现库：Optuna 4.9.0，`TPESampler`。
- 超参数：`n_startup_trials=5`、`multivariate=false`。
- seed：`SeedRegistry.optuna_sampler`，其值只能来自 `ExperimentConfig.seed`。
- ask/tell：`study.ask()` 创建 trial，使用 `suggest_float`/`suggest_int`/`suggest_categorical`；成功时把统一 ObjectiveEvaluator 的标量交给 `study.tell()`。
- failure：仿真、解析或参数失败映射为 Optuna `TrialState.FAIL`，不提交数值，也不把 `1e100` 写入记录。
- phase：startup trial 记录为 `initialization`，之后记录为 `model_based`。
- resume：在 tell 后把 in-memory Study（包括 sampler RNG）序列化为 base64 包装的 JSON，同时记录精确 Optuna 版本和反馈历史。
- 限制：pickle 状态只允许在相同锁定 Python/Optuna 环境中加载，不应读取不可信状态文件。

## Bayesian Optimization

- 实现：CircuitPilot 内部 Gaussian Process；使用已有 NumPy 1.24+、SciPy 1.10+，未新增 scikit-learn/scikit-optimize。
- 选择理由：避免为两个 RC 连续变量增加重量级依赖，同时保留可审计的逐候选 ask/tell、RNG 和 surrogate 数据。
- 超参数：`initial_random_points=5`、`candidate_pool_size=512`、`exploration_xi=0.01`、`noise=1e-8`。
- surrogate：单位超立方体上的 Matérn-5/2 kernel；以 Expected Improvement 在 seeded candidate pool 中选择下一点。
- phase：固定初始化阶段为 `initialization`；有足够成功观测后为 `model_based`。
- failure：失败 observation 不进入 GP，也不被赋予 penalty；预算仍由 Runner 消耗。
- resume：JSON 保存 RNG、成功的 X/y、phase、pending candidate 和完整反馈。
- 限制：Task 2 只支持 float/log-float；不声称支持 int 或 categorical。kernel 超参数固定，本阶段不做超参数拟合。

## 依赖与版本

Task 2 唯一新增运行依赖为 Optuna。研究锁文件精确固定 Optuna 4.9.0 及 Alembic、SQLAlchemy、Mako、colorlog、tqdm 等传递依赖。BO 和 DE 使用已有 NumPy/SciPy，不依赖 scikit-learn。manifest 记录 Optuna、NumPy、SciPy、Python、CircuitPilot 与 ngspice 版本以及 ngspice 二进制 SHA-256。

## 记录、恢复和统计

所有方法共享同一 CSV/SQLite schema，并新增 `optimizer_phase` 与 `is_feasible`。summary 保留预算计数、ngspice 调用数、最佳参数/指标、首次可行 iteration、总时间和平均仿真时间。恢复允许显式增加总预算，但不能减少预算或改变 search space、method、seed、目标、约束、成功判据、仿真配置或 optimizer hyperparameters。

`simulations_to_first_feasible` 的未成功 run 是右删失数据，保存为 null。当前基础统计的 median 只对观测到首次可行的 run 计算，并单独输出 `censored_runs`；绝不把删失值替换为 0 或 budget+1。
