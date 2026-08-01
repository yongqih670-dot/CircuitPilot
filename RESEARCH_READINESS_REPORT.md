# CircuitPilot 研究就绪审计报告

审计日期：2026-08-01（Asia/Shanghai）

审计基线：`bfa3271c908dca1bb14bcdd15208557774cf485d`

审计环境：Windows 10 Home China、Python 3.12.7、ngspice-46（KLU）

## 结论

**自动仿真、参数扫描和优化工作流在本次审计环境中达到研究就绪状态。** 三种电路模板、离散扫描、SciPy 连续优化、结果解析、绘图和 SQLite 自动保存均通过真实 ngspice 测试；生产代码中没有 mock、fake、placeholder、demo fallback、hardcoded result 或 random result。ngspice 缺失、进程非零退出、超时和不可解析输出都会明确失败，不会生成默认物理指标。

该结论只覆盖自动工作流及报告所列环境。保留的 `experiment create` 是人工历史导入接口，其指标是用户提供的未验证数据，不能作为 ngspice 研究证据。Linux/macOS、其他 Python/ngspice/SciPy 版本以及长时间大规模优化仍属于未验证风险。

## 审计方法与搜索结果

对整个仓库（排除 `.git`、二进制 ngspice 工具和既有输出目录）进行了不区分大小写的代码搜索。

生产代码搜索表达式：

```text
(mock|fake|placeholder|demo[ _-]*fallback|hard[ _-]*coded[ _-]*result|
 random[ _-]*result|default[ _-]*result|synthetic[ _-]*result|dummy[ _-]*result)
```

真实输出：

```text
NO MATCHES IN PRODUCTION CODE
```

全仓库 `mock|fake|placeholder` 命中仅位于 `tests/test_circuit_optimizer.py`、`tests/test_parameter_sweep.py` 和 `tests/test_simulator.py`，均为隔离外部进程或 SciPy 的单元测试替身。真实集成测试没有 monkeypatch、fake response 或合成 AC 数据。

`demo fallback|fallback|hardcoded result|random result|default result|synthetic result|dummy result` 的全仓库搜索结果为：

```text
NO MATCHES
```

生产代码中的随机相关命中仅为优化器 `seed` 的读取、校验和保存。代码不生成随机性能结果。`FAILED_OBJECTIVE_PENALTY = 1e100` 只是在单个候选仿真失败时交给 SciPy 的内部排序惩罚；对应历史行的 `metric_value` 为 `None`/CSV 空值。如果所有候选失败，优化直接抛出 `OptimizationError`，不会把惩罚值当作物理指标返回。

## 指标来源验证

自动工作流的数据流如下：

```text
YAML / CLI 参数
  → 生成 .cir 网表
  → ngspice 写入 ac_results.dat
  → parse_ac_output 解析频率、增益和相位
  → 截止频率 / 增益 / 功耗指标
  → CSV、图、优化器、SQLite 和 research_manifest.json
```

逐项代码核查与测试结果：

| 指标或记录 | 来源 | 验证结果 |
|---|---|---|
| 频率、增益、相位 | `parse_ac_output(ac_results.dat)` | 真实 ngspice 输出；非数值、非有限值、非递增频率或空数据均报错 |
| 低通截止频率 | 解析后的增益曲线下降穿越 −3 dB | 真实值与 `1/(2πRC)` 在 2% 内一致 |
| 高通截止频率 | 解析后的增益曲线上升穿越 −3 dB | 真实值与 `1/(2πRC)` 在 2% 内一致 |
| 分压器增益 | 解析后的 AC 增益 | 真实值与 `20log10(Rbottom/(Rtop+Rbottom))` 一致 |
| 优化 bandwidth | 每个候选的解析曲线和截止频率 | 真实 10 次 ngspice 评估通过 |
| 优化 gain | 指定频率处对解析增益作对数频率插值 | 使用真实低通 AC 输出验证 |
| 优化 power | 由解析增益、解析相位、配置 R 和 1 V 峰值激励计算 | 使用真实低通 AC 输出验证；不是 ngspice 的直接功率测量 |
| SQLite 自动实验 | 上述自动工作流产生的参数、指标和实测耗时 | 端到端读取数据库并与重新解析的原始输出交叉核对 |

`sample_count` 来自解析行数，`gain_at_start_db`、`phase_at_start_deg` 和 `transfer_gain_db` 来自解析数组。扫描的相对误差及优化的目标值都是由真实物理指标进一步计算的派生量。

## 错误传播验证

- 找不到 ngspice：在运行前抛出明确错误，CLI 返回 `1`，不创建原始结果或成功研究清单。
- ngspice 返回非零状态：保存日志并抛出包含退出码的 `SimulationError`。
- ngspice 超时或无法启动：抛出 `SimulationError`。
- 输出缺失、空、格式错误、非有限值或频率顺序错误：抛出 `ParseError`。
- 单个扫描/优化候选失败：保留失败状态和错误信息，物理指标为空；其他候选可以继续。
- 所有优化候选失败：保留原子更新的 `optimization_history.csv` 后抛出 `OptimizationError`，不返回最佳默认值。
- 成功研究清单要求目录内至少存在网表、ngspice 日志和原始输出；缺失时抛出 `ResearchArtifactError`。

## 可复现实验目录

单次仿真、参数扫描和自动优化成功后，`--output-dir` 被定义为该次实验的证据边界。新增的 `research_manifest.json` 保存：

- 完整解析后配置和原始 YAML 的逐字节副本 `input_config.yaml`；
- 随机种子（确定性工作流为 `null`）；
- 参数、指标、工作流类型、电路类型；
- UTC 开始/结束时间和实测运行时间；
- 实际解析到的 ngspice 可执行文件路径；
- SQLite 实验名称和数据库 ID（如果启用自动保存）；
- 目录内所有网表、日志、原始数据、CSV、JSON 和图的相对路径、类型、字节数与 SHA-256。

每个扫描或优化候选继续保存在独立的 `runs/run_*` 或 `runs/evaluation_*` 子目录，包含 `.cir`、`ngspice.log` 和 `ac_results.dat`。为避免不同运行的证据混合，研究运行必须为每次命令指定新的 `--output-dir`；当前版本没有强制拒绝复用已有目录，此项列为剩余风险。

## 新增端到端覆盖

`tests/test_research_readiness_e2e.py` 不使用 mock 或 monkeypatch，覆盖：

1. 三种 YAML 电路配置分别生成网表并调用真实 ngspice；
2. 解析原始 AC 输出并校验低通、高通、分压器结果；
3. 配置 → 参数生成 → 网表 → ngspice → 解析 → SciPy 优化；
4. 优化历史、最佳候选、研究清单和文件哈希；
5. SQLite 自动保存后重新读取，并与原始输出重算值交叉核对；
6. ngspice 缺失、真实 ngspice 非零退出和不可解析输出；
7. gain 与 power 对真实解析响应的计算。

`tests/test_research_artifacts.py` 覆盖清单、种子、配置副本、哈希和证据缺失拒绝。`tests/test_circuit_optimizer.py` 新增全候选失败时不生成指标且保留失败历史的回归测试。

## 全新环境验证

`scripts/clean_environment_test.py` 会：

1. 创建全新临时虚拟环境；
2. 移除 `PYTHONPATH` 并禁止用户 site-packages；
3. 从当前项目和 `pyproject.toml` 声明重新构建、安装 wheel 与运行依赖；
4. 在项目目录外调用已安装的 `python -m circuitpilot`；
5. 使用真实 ngspice 完成确定性截止频率优化；
6. 核验配置副本、清单、历史、摘要、图、候选网表/日志/原始数据和 SQLite 记录；
7. 成功校验并关闭数据库后清理临时环境。

本次真实运行安装了 CircuitPilot 0.5.0、PyYAML 6.0.3、matplotlib 3.11.1、NumPy 2.5.1 和 SciPy 1.18.0。关键原始输出如下：

```text
Successfully built circuitpilot
Successfully installed PyYAML-6.0.3 circuitpilot-0.5.0 ... scipy-1.18.0 ...
installed CircuitPilot 0.5.0
Automatic optimization completed.
Circuit type: rc_lowpass
Objective: target bandwidth
Best resistance: 1077.70127532 ohm
Best capacitance: 1.5052226272e-07 F
Best metric: 978.633426319
Best optimizer objective: 0.0213665736811
Evaluations: 10 total, 10 succeeded, 0 failed
Experiment saved with ID 1.
clean_environment_test: PASS
```

## 全部测试的真实输出

完整测试：

```text
........................................................................ [ 65%]
......................................                                   [100%]
110 passed in 4.69s
```

真实 ngspice 集成测试：

```text
collected 110 items / 102 deselected / 8 selected
tests/test_integration.py::test_real_ngspice_rc_lowpass_end_to_end PASSED
tests/test_integration.py::test_real_ngspice_two_point_parameter_sweep PASSED
tests/test_integration.py::test_real_ngspice_scipy_optimization_loop PASSED
tests/test_research_readiness_e2e.py::test_every_circuit_template_uses_real_ngspice_output[lowpass.yaml] PASSED
tests/test_research_readiness_e2e.py::test_every_circuit_template_uses_real_ngspice_output[highpass.yaml] PASSED
tests/test_research_readiness_e2e.py::test_every_circuit_template_uses_real_ngspice_output[voltage_divider.yaml] PASSED
tests/test_research_readiness_e2e.py::test_config_to_real_optimization_to_database_and_manifest PASSED
tests/test_research_readiness_e2e.py::test_real_ngspice_nonzero_exit_is_an_error PASSED
8 passed, 102 deselected in 2.73s
```

不依赖 ngspice 的单元/数据库测试：

```text
........................................................................ [ 70%]
..............................                                           [100%]
102 passed, 8 deselected in 2.20s
```

本次没有 skipped、failed 或 xfailed 测试。

## 审计中发现并修复的问题

1. **缺少统一的研究运行清单。** 已增加配置快照、种子、参数、指标、耗时、可执行文件和证据哈希清单，并接入单次、扫描和优化 CLI。
2. **全候选优化失败时，最终历史可能因异常而没有统一导出。** 现改为每次评估后原子更新历史；所有候选失败仍保留空指标和错误原因。
3. **缺少覆盖优化和数据库保存的无替身端到端测试。** 已增加真实 ngspice E2E，并从原始数据重新计算指标与数据库交叉验证。
4. **高通、分压器及 gain/power 缺少统一研究审计证据。** 已增加真实模板和真实响应指标测试。
5. **缺少全新环境安装验证。** 已增加并真实运行 `clean_environment_test.py`；修复了 Windows 子进程 UTF-8 输出和 SQLite 连接清理问题。

## 仍未验证的风险

- `experiment create` 接受人工 JSON 指标。它为兼容第四阶段而保留，并已在 README 明确标记为未验证导入；研究证据必须使用自动工作流及其清单。
- `--output-dir` 是实验边界，但程序尚未强制目录为空或自动生成唯一运行 ID；复用目录可能混入旧文件。
- 清单记录依赖配置和 ngspice 路径，但尚未记录 Python/库版本、操作系统、ngspice 版本文本或二进制哈希；跨版本仅靠种子不保证逐位相同。
- 功耗是由 ngspice 的传递函数增益/相位和理想 1 V 激励推导，不是通过器件电流或瞬态积分直接测得；更复杂器件模型下需要重新定义与验证。
- 当前只在 Windows、Python 3.12.7、ngspice-46 上完成真实审计；Linux、macOS、Python 3.10/3.11/3.13 和其他 ngspice 版本未验证。
- 当前 E2E 使用小型 RC 搜索空间和短优化；长时运行、中断恢复、并发实验、数据库锁竞争和大规模扫描未做压力测试。
- 绘图测试验证文件成功生成且非空，没有进行逐像素或人工视觉基准审查。
- 依赖使用兼容范围而非锁文件；本次 clean test 可复现安装，但未来包索引解析到的新版本仍可能改变数值或行为。

在用于论文或长期实验前，建议优先解决输出目录唯一性、环境/二进制指纹和依赖锁定三项风险。
