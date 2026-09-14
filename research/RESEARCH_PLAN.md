# CircuitPilot 研究计划

## 当前任务

Research Task 1 建立统一实验基础设施与优化器基线框架。当前只验证已经通过研究审计的 RC low-pass 电路和 random search，不引入新的电路模型。

本任务的交付边界：

- 一个严格校验的 `ExperimentConfig`；
- 一个不接触仿真器的 `Optimizer.ask/tell` 接口；
- 一个对所有方法相同的 `ExperimentRunner`；
- 统一 simulation budget、随机种子、CSV、SQLite、目录和 manifest；
- 两个真实 ngspice 最小实验，seed 分别为 0 和 1。

## 明确不在当前范围内

- LLM Agent 或自主工具规划；
- PVT corner、Monte Carlo 或 process model；
- Failure-aware proposal、retry policy 或 failure classifier；
- Optuna/TPE、贝叶斯优化或强化学习实现；
- OTA、晶体管级新电路和 Web UI。

## 后续研究门槛

任何新方法进入比较前，必须实现同一个 `Optimizer` 接口，并通过相同配置、预算、仿真器、指标、种子和记录格式的协议测试。任何方法不得直接调用 ngspice，也不得在内部重新计算物理指标。
