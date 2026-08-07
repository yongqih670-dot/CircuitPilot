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

合并前必须运行 `FairnessValidator`。校验项目至少包括 search-space SHA-256、电路、总预算、PVT、metric/objective/constraint 定义、seed 集合、success criterion、ngspice 配置、ngspice 版本和可执行文件 SHA-256、CircuitPilot/Git/Python/NumPy/SciPy/Optuna 版本。公平基线必须来自 clean Git worktree。任何不一致必须抛出 `FairComparisonError`，不得生成 comparison CSV 或图。

## 预算定义

一个候选槽最多允许一次真实 ngspice 启动。ngspice 成功、非零退出、超时或输出解析失败都会消耗该槽，预算不会返还。越界或格式非法的候选不会调用 ngspice，但同样消耗一个候选槽，避免算法通过免费重试获得额外搜索机会。

必须记录：

- `evaluations_total`；
- `evaluations_success`；
- `evaluations_failed`；
- `budget_remaining`；
- `ngspice_calls`。

达到预算后，Runner 必须在下一次 `ask` 之前停止。

算法的一次 initialization、population member、trial 或 surrogate suggestion 都属于普通 candidate，不享有免费评估。generation 未完成、sampler startup 未完成或模型希望追加样本均不能成为超预算理由。

## 随机性

`ExperimentConfig.seed` 是唯一允许的种子入口。Python `random`、NumPy legacy RNG、NumPy Generator、SciPy `random_state` 和未来 Optuna sampler 均使用 manifest 中登记的统一 seed registry。优化器的局部配置不得再次声明 seed。

## 数据来源

成功记录中的物理指标必须来自相应 evaluation 目录内的真实网表、ngspice 日志和原始输出。失败记录的 `raw_metrics` 必须为空，`objective_value` 与 `constraint_violation` 必须为空；不得用 penalty、默认值或理论公式冒充仿真结果。

统一可行性定义写在 ExperimentConfig。RC Task 2 使用：

```text
relative_error = abs(simulated_fc - target_fc) / target_fc
is_feasible = relative_error <= 0.05 and constraint_violation == 0
```

未在预算内成功的 run，其 `simulations_to_first_feasible` 必须是 null。基础 median 只报告观测到事件的 run，并同时报告 `censored_runs`；若使用更高级删失统计，必须另行预注册。禁止默认为 0 或 budget+1。

## State 与恢复

四种方法都必须在每次 tell/record 后保存状态。显式 resume 可以提高总 simulation budget，并从 SQLite 中已记录的 iteration 继续；不得降低预算，不得修改任何其他实验语义，不得重新评估已有 iteration。恢复前后的总预算仍是一个上限，而不是两段预算之和。

## 图表

baseline convergence、success-rate、best-objective 和 first-feasible 图只能读取 canonical `evaluations.csv`。失败 objective 不得插值或填充。首次可行分布图可以只展示未删失观测，但必须在标题或说明中明确删失 run 被排除。

## 结果审计

每个 run 必须保留 `experiment_config.yaml`、`evaluations.csv`、SQLite、optimizer state、每个候选的证据目录、summary、plot 和 `research_manifest.json`。manifest 必须包含环境指纹、Git commit、依赖版本、ngspice 版本与二进制 SHA-256，以及全部产物的 SHA-256。
