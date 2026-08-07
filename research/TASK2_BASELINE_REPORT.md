# Research Task 2 Baseline Report

## 范围

本任务只在已审计的 RC low-pass 上建立 Random Search、Differential Evolution、Optuna TPE 和 Gaussian-process Bayesian Optimization 四个传统基线。没有实现 LLM Agent、failure-aware、PVT-aware、动态搜索空间、新复杂电路或 Web UI。

## 实现结果

- 四个 optimizer 共享 `ask/tell/save_state/load_state`，全部通过同一 `ExperimentRunner`。
- DE 使用逐候选 generation state machine，可在半代严格停在预算边界。
- TPE 使用 Optuna 4.9.0 `TPESampler`；失败 trial 使用 `FAIL`，没有数值 penalty。
- BO 使用内部 Matérn-5/2 GP + Expected Improvement，区分 initialization/model_based。
- Random 支持 float、int、categorical 和 log-float。
- CSV/SQLite 统一增加 `optimizer_phase` 和 `is_feasible`。
- summary 增加首次可行、总 runtime、平均仿真时间及完整预算计数。
- `FairnessValidator` 在生成比较表前强制检查所有协议字段和 seed set。
- batch CLI 生成 `baseline_results.csv`、`baseline_summary.csv` 和四类真实数据图。
- 四种 optimizer 均验证了 10 次保存、退出、恢复到 20 次的确定性序列和预算连续性。

## 主要文件

- 配置/Runner/记录：`src/circuitpilot/experiments/config.py`、`runner.py`、`recorder.py`、`objectives.py`
- Optimizer adapters：`src/circuitpilot/experiments/optimizers/`
- 比较层：`fairness.py`、`statistics.py`、`baseline_plots.py`、`batch.py`
- 固定配置：`experiments/configs/rc_baseline_*.yaml`
- 依赖：`pyproject.toml`、`requirements-research.lock`
- 测试：`tests/test_task2_optimizers.py`、`test_task2_fairness.py`、`test_task2_integration.py`

## 测试证据

实现后的完整测试：

```text
168 passed in 12.74s
```

分组复跑：

```text
151 passed, 17 deselected in 4.57s
17 passed, 151 deselected in 10.85s
```

其中新增的算法与公平性单元测试为 17 passed；新增的四方法真实 ngspice 集成测试为 4 passed。

锁文件驱动的全新环境测试也已通过：在临时 Python 3.12 venv 安装 30 个精确固定依赖，`pip check` 返回 `No broken requirements found`；随后构建/安装 CircuitPilot wheel，执行 10 次真实 ngspice legacy optimization，并核验 SQLite、manifest、网表、日志和 AC 原始输出，最终输出 `clean_environment_test: PASS`。

## 真实小规模 baseline

运行条件：RC low-pass，methods = random/de/tpe/bo，seeds = 0/1/2，每个 run budget = 20，success threshold = 5%。总计 12 个 run、240 个候选。

证据审计：

- `evaluations_total = 240`
- `ngspice_calls = 240`
- `evaluations_success = 240`
- `evaluations_failed = 0`
- evaluation directories/netlists/logs/raw AC outputs 均为 240
- 失败记录中的伪造指标数为 0

方法级框架验证结果：

| method | runs | success rate | median best objective | median simulations to first feasible | censored runs | ngspice calls |
|---|---:|---:|---:|---:|---:|---:|
| Random | 3 | 0.0000 | 0.127425 | null | 3 | 60 |
| DE | 3 | 0.0000 | 0.127425 | null | 3 | 60 |
| TPE | 3 | 0.3333 | 0.077753 | 15 | 2 | 60 |
| BO | 3 | 0.3333 | 0.080673 | 20 | 2 | 60 |

这些数据只验证框架和证据链。样本仅 3 个 seeds、预算仅 20，不构成任何算法优劣结论。

## 统计解释

未找到 feasible solution 的 run 将 `simulations_to_first_feasible` 保存为 null，并计入 `censored_runs`。当前 median 只使用观察到首次可行事件的 run；未成功 run 没有被替换成 0 或 budget+1。best-objective 统计只使用确实存在的成功仿真 objective；failure rate 使用全部 candidate evaluation。

## 已知限制与未解决风险

- 当前比较仅验证 RC low-pass；不能外推到晶体管级电路。
- BO 仅支持连续/log-continuous 变量，使用固定 kernel 超参数和离散 EI candidate pool。
- DE 当前仅支持连续变量以及 `best1bin`/`rand1bin`。
- TPE resume 状态依赖锁定的 Python/Optuna 版本，并使用本地可信 pickle payload。
- 3 seeds × 20 budget 的验证规模过小；没有进行统计显著性或 survival analysis。
- Task 2 按要求没有 PVT 或 failure-aware 行为。

未发现会破坏 v0.5 research baseline 或导致隐藏额外 ngspice evaluation 的已知功能问题。

## 下一阶段边界

后续工作应先扩大预注册 seed/budget 规模并保持当前协议，之后才能单独进入 PVT 或 failure-aware 研究。不得以修改本 Task 2 的搜索空间、成功判据或 Simulator 作为提升某种算法结果的手段。
