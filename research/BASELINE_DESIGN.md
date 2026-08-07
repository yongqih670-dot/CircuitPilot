# Research Task 1 基线设计

## 架构

```text
ExperimentConfig
      |
      v
Optimizer.ask() -> ExperimentRunner -> CircuitPilot netlist/simulator -> ngspice
      ^                                      |
      |                                      v
Optimizer.tell() <- ObjectiveEvaluator <- Analyzer <- parsed AC output
                          |
                          v
                 CSV + SQLite recorder
```

`Optimizer` 只知道参数、外部返回的 metrics、objective 和 simulation status。它既不能导入 simulator，也不能读取 ngspice 文件。`ExperimentRunner` 只依赖接口，不对 `random` 或未来方法编写专用循环。

## 当前物理基线

当前研究实例只允许 `rc_lowpass`。网表生成、ngspice 子进程检查、AC 输出解析和截止频率插值直接复用 v0.5 research baseline 已审计代码。带宽、增益、相位和兼容的 `derived_rc_power` 只能由 Analyzer 从解析响应提取。

## Random baseline

RandomOptimizer 对线性范围使用 uniform，对对数范围使用 log-uniform。候选顺序完全由 `ExperimentConfig.seed` 初始化的 NumPy Generator 决定。每次 `ask` 必须有且只有一次配对的 `tell`，RNG state 和历史在每个 candidate 后原子保存。

## 统一记录

`evaluations.csv` 与 `evaluations.sqlite3` 保存同一个 schema。参数和 raw metrics 使用排序 JSON，其他列保持标量形式。SQLite 是恢复依据，CSV 在每次提交后由 SQLite 顺序重建，以降低中断造成的双写不一致风险。

## 恢复边界

只有显式 `resume` 才允许进入已有 run。恢复要求 run context、配置 identity hash、`experiment_config.yaml`、SQLite 历史和 optimizer state 全部匹配。恢复后的预算从已经持久化的 evaluation 数量继续计算，不重新赠送预算。
