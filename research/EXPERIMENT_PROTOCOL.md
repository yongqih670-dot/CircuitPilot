# CircuitPilot 公平实验协议

## 强制公平条件

论文或报告中的算法比较必须同时满足：

- 所有算法使用完全相同的 search space；
- 所有算法使用完全相同的 simulation budget；
- 所有算法使用完全相同的 circuit；
- 所有算法使用完全相同的 PVT 条件（从后续 PVT 阶段开始）；
- 所有算法使用完全相同的 metrics 和目标/约束定义；
- 所有算法使用完全相同的 seeds 集合；
- 所有算法通过完全相同的 CircuitPilot Simulator 与 Analyzer；
- 所有算法使用完全相同的 success criteria 与 failure classification。

任一条件不同的结果不得放入同一公平比较表。

## 预算定义

一个候选槽最多允许一次真实 ngspice 启动。ngspice 成功、非零退出、超时或输出解析失败都会消耗该槽，预算不会返还。越界或格式非法的候选不会调用 ngspice，但同样消耗一个候选槽，避免算法通过免费重试获得额外搜索机会。

必须记录：

- `evaluations_total`；
- `evaluations_success`；
- `evaluations_failed`；
- `budget_remaining`；
- `ngspice_calls`。

达到预算后，Runner 必须在下一次 `ask` 之前停止。

## 随机性

`ExperimentConfig.seed` 是唯一允许的种子入口。Python `random`、NumPy legacy RNG、NumPy Generator、SciPy `random_state` 和未来 Optuna sampler 均使用 manifest 中登记的统一 seed registry。优化器的局部配置不得再次声明 seed。

## 数据来源

成功记录中的物理指标必须来自相应 evaluation 目录内的真实网表、ngspice 日志和原始输出。失败记录的 `raw_metrics` 必须为空，`objective_value` 与 `constraint_violation` 必须为空；不得用 penalty、默认值或理论公式冒充仿真结果。

## 结果审计

每个 run 必须保留 `experiment_config.yaml`、`evaluations.csv`、SQLite、optimizer state、每个候选的证据目录、summary、plot 和 `research_manifest.json`。manifest 必须包含环境指纹、Git commit、依赖版本、ngspice 版本与二进制 SHA-256，以及全部产物的 SHA-256。
