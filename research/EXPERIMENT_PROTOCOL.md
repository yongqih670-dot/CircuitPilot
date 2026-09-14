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

## Research Task 3 晶体管级扩展

Task 2 的全部公平性规则继续强制执行。晶体管级比较还必须具有完全一致的
`benchmark_config_hash`、模型库 SHA-256、模型名、section/corner、拓扑固定值、
`.op`/`.ac` 设置、归一化约束、可行性合取条件和 scalar objective 公式。

每个 candidate 消耗一个预算槽，最多启动一个包含 `.op + .ac` 的真实 ngspice
进程。证据目录必须保存网表、ngspice 日志、原始 AC 数据、原始 DC 工作点以及
可用的 MOS 工作点数据。失败必须保存类型、消息、可取得的返回码和 timeout 状态。

Calibration 是单独预注册的确定性网格，不得进入 baseline `evaluations.csv`、
summary、plot、seed set 或算法结论。benchmark hash 冻结后，任何语义修改都会使
旧 hash 下的全部 run 失效，四种方法必须从 seed 0 重新开始。

`is_feasible` 仅表示所有硬约束同时满足。删失 run 继续保持
`simulations_to_first_feasible = null`，同时记录 survival-ready 的
`event_observed` 和 `evaluation_time`；不得替换为 0 或 budget+1。

## Research Task 4 SKY130 与删失语义扩展

Task 4 公平比较还必须共享完全一致的 SKY130 model-tree SHA-256、top-library
SHA-256、PDK release/commit、device/corner、带宽语义版本、固定 AC measurement
window、censoring policy 和 benchmark difficulty protocol version。任何不一致
必须由 `FairnessValidator` 拒绝。

有效频响在固定 `f_stop` 前没有 post-peak -3 dB crossing 时是
`right_censored`：精确 `bandwidth_hz` 保持 null，只记录
`bandwidth_lower_bound_hz=f_stop`。它不是 simulation failure。只有 `>=` 带宽
硬约束可使用该下界作确定性判定，精确带宽统计和散点图不得使用此下界冒充测量值。

Time-to-first-feasible 的未成功 run 在预算处右删失。正式输出必须同时提供
逐点 Kaplan–Meier survival probability、KM median（可定义时）和固定预算 horizon
上的 RMST。`simulations_to_first_feasible` 对删失 run 继续保持 null。
