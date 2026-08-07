# CircuitPilot

> 研究审计状态和真实测试证据见 [RESEARCH_READINESS_REPORT.md](RESEARCH_READINESS_REPORT.md)。

研究冻结版本：`v0.5-research-baseline`。

CircuitPilot 是一个采用 `src/` 目录结构的参数化 ngspice 电路仿真与自动优化平台。它可以从 YAML 读取单次仿真、离散参数扫描或连续优化配置，并将仿真过程与设计结果归档到 SQLite。

当前第五阶段支持：

- RC low-pass filter；
- RC high-pass filter；
- Voltage divider；
- YAML 配置读取、严格校验和不可变 Python 配置对象；
- ngspice AC 分析、频率/增益/相位解析和波特图；
- 低通下降穿越与高通上升穿越的 −3 dB 截止频率；
- R/C 参数范围和离散值的笛卡尔积扫描；
- 相对误差计算与 Top-N 方案排名；
- 全部实验结果 CSV 和“参数变化—性能”曲线；
- SQLite 实验创建、查询、最优结果与历史比较；
- 基于 SciPy 差分进化的连续 R/C 自动优化；
- 最大化增益、最小化功耗和目标带宽三类目标函数；
- 每一次优化评估的 CSV/运行目录、JSON 摘要和收敛曲线；
- 单组失败隔离、ngspice 缺失预检和每组独立运行目录。

前四阶段的 API 和命令行方式继续保留。

## 项目结构

```text
.
├── main.py
├── pyproject.toml
├── README.md
├── examples/
│   ├── lowpass.yaml
│   ├── highpass.yaml
│   ├── voltage_divider.yaml
│   ├── sweep_lowpass.yaml
│   └── optimize_rc_cutoff.yaml
├── src/circuitpilot/
│   ├── analysis.py
│   ├── circuit_config.py
│   ├── circuit_optimizer.py       # SPICE 指标评估、SciPy 优化、历史与曲线
│   ├── cli.py
│   ├── exceptions.py
│   ├── experiment_manager.py       # SQLite 实验历史、最优结果与比较
│   ├── netlist.py                 # 第一阶段兼容 API
│   ├── netlist_generator.py
│   ├── optimization_config.py     # 优化目标、参数边界和 YAML 校验
│   ├── parameter_sweep.py         # 执行、排名、CSV、性能图
│   ├── parser.py
│   ├── plotting.py
│   ├── simulator.py
│   └── sweep_config.py            # 扫描 YAML 与参数组合
└── tests/
```

## 环境与安装

要求 Python 3.10 或更高版本。运行依赖为 PyYAML、matplotlib 和 SciPy，测试依赖为 pytest。

CircuitPilot 按以下顺序查找 ngspice：

1. `--ngspice` 指定的名称或完整路径；
2. 系统 `PATH`；
3. 项目内的 `tools/ngspice/bin/ngspice_con.exe`。

当前工作区已在第三种位置安装官方 Windows x64 便携版 ngspice 46，因此从项目根目录运行时无需修改系统 `PATH`。Windows 官方包同时含有 `ngspice.exe` 和 `ngspice_con.exe`，批处理仿真会优先使用可正常返回输出和退出码的控制台版本 `ngspice_con.exe`。

先确认 ngspice 可用：

```console
ngspice --version
```

项目本地 Windows 安装可直接检查：

```powershell
.\tools\ngspice\bin\ngspice_con.exe -v
```

PowerShell 安装项目：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

论文实验或研究复现应使用完全锁定的 Python 3.12 / Windows 依赖环境：

```powershell
python -m pip install -r requirements-research.lock
python -m pip install --no-deps --no-build-isolation .
```

Bash/zsh：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## 自动参数扫描

示例 [examples/sweep_lowpass.yaml](examples/sweep_lowpass.yaml)：

```yaml
circuit: rc_lowpass

target:
  cutoff_frequency: 10000

parameters:
  R:
    min: 100
    max: 10000
    step: 100
  C:
    values:
      - 1e-9
      - 10e-9
      - 100e-9

top_n: 10
```

运行扫描：

```console
python main.py --sweep-config examples/sweep_lowpass.yaml
```

指定输出目录、ngspice 路径和每组超时：

```powershell
python main.py --sweep-config examples\sweep_lowpass.yaml `
  --output-dir output\sweep_lowpass `
  --ngspice "C:\path\to\ngspice.exe" `
  --timeout 120
```

安装项目后也可以使用：

```console
python -m circuitpilot --sweep-config examples/sweep_lowpass.yaml
circuitpilot --sweep-config examples/sweep_lowpass.yaml
```

### 扫描配置规则

`circuit` 可省略，默认是 `rc_lowpass`；也可设置为 `rc_highpass`。分压器没有截止频率，因此不能用于当前截止频率优化。

目标字段支持两种等价写法：

```yaml
target:
  cutoff_frequency: 10000
```

或：

```yaml
target:
  cutoff_frequency_hz: 10000
```

R 和 C 均可使用离散值：

```yaml
R:
  values: [100, 220, 470, 1000]
```

或从 `min` 开始按 `step` 递增、且不超过 `max` 的范围：

```yaml
R:
  min: 100
  max: 1000
  step: 100
```

科学计数法既可由 YAML 解析为数字，也可写成字符串；`1e-9`、`10e-9` 等写法均受支持。重复值、非正数、未知字段、错误范围和超过 100000 组的扫描会被拒绝。

`analysis` 为可选项。省略时，CircuitPilot 根据 R/C 参数空间的理论最小和最大截止频率自动生成带余量的 AC 扫频区间。也可以显式覆盖：

```yaml
analysis:
  start_frequency_hz: 10
  stop_frequency_hz: 10000000
  points_per_decade: 100
```

### 计算与排名

每组成功仿真按以下公式计算误差：

```text
relative_error = abs(simulated_cutoff - target_cutoff) / target_cutoff
```

CLI 按误差从小到大打印 `Top 10 solutions`。可以通过根字段调整数量：

```yaml
top_n: 20
```

如果某一组网表、ngspice 或解析失败，该组被标记为 `failed`，其余组合继续执行。若 ngspice 不存在，则在创建组合运行目录前立即终止。

### 扫描输出

默认输出到 `output/`：

```text
output/
├── sweep_results.csv
├── parameter_performance.png
└── runs/
    ├── run_0001/
    │   ├── rc_lowpass.cir
    │   ├── ac_results.dat
    │   └── ngspice.log
    └── ...
```

CSV 包含：

- 组合编号和成功方案排名；
- R、C 和目标截止频率；
- 仿真截止频率和相对误差；
- `success`/`failed` 状态及失败原因。

性能图以 R 为横轴、仿真截止频率为纵轴，每个 C 值绘制一条曲线，并标记目标截止频率。

## 自动优化

第五阶段使用 `scipy.optimize.differential_evolution` 在连续 R/C 空间中搜索。优化器生成候选参数后，CircuitPilot 为每组参数生成网表、调用 ngspice、解析 AC 响应、计算目标值，再把目标值返回给优化器。

截止频率优化示例 [examples/optimize_rc_cutoff.yaml](examples/optimize_rc_cutoff.yaml)：

```yaml
circuit:
  type: rc_lowpass

objective:
  metric: bandwidth
  goal: target
  target_value: 10000

parameters:
  R:
    min: 500
    max: 5000
    scale: log
  C:
    min: 1e-9
    max: 100e-9
    scale: log

optimizer:
  max_iterations: 6
  population_size: 5
  tolerance: 0.001
  seed: 42
  polish: true
```

运行并自动保存到实验数据库：

```powershell
python main.py --optimize-config examples\optimize_rc_cutoff.yaml `
  --output-dir output\rc_cutoff_optimization `
  --experiment-name "RC low-pass 10 kHz automatic optimization"
```

安装项目后也可以运行：

```console
python -m circuitpilot --optimize-config examples/optimize_rc_cutoff.yaml
circuitpilot --optimize-config examples/optimize_rc_cutoff.yaml
```

### 优化目标

当前支持以下三种严格组合：

| metric | goal | 含义 | 必需字段 |
|---|---|---|---|
| `gain` | `maximize` | 最大化指定频率的输出增益（dB） | `evaluation_frequency_hz` |
| `power` | `minimize` | 最小化指定频率的电阻平均耗散功率（W） | `evaluation_frequency_hz` |
| `bandwidth` | `target` | 使 −3 dB 带宽接近目标值（Hz） | `target_value` |

兼容的 RC 功耗使用 1 V 峰值 AC 激励，根据真实 ngspice 增益/相位推导低通串联电阻或高通输出电阻耗散。研究记录将其明确标记为 `derived_rc_power`，同时保留原 `power_w` 数值别名。它不等同于晶体管电路的电源功耗。

晶体管级研究可使用独立接口 `circuitpilot.dc_supply_power(vdd_voltage_v, supply_current_a)`，定义为 `abs(VDD * I(VDD))`。当前仅建立功耗接口和真实 ngspice 工作点测试，没有增加 OTA 或新的电路模板。带宽目标的优化误差为：

```text
objective = abs(simulated_bandwidth - target_bandwidth) / target_bandwidth
```

`parameters.R` 和 `parameters.C` 都必须包含 `min`、`max`，`scale` 可为 `log`（默认）或 `linear`。`optimizer` 可省略；默认使用 10 代、种群系数 8、随机种子 42，并执行最终局部精修。`analysis` 与扫描配置相同，可以显式提供；省略时会根据 R/C 极值与目标频率自动推导。

自动优化目前支持 `rc_lowpass` 和 `rc_highpass`。每个失败候选会记录错误并向优化器返回惩罚值，其余候选继续运行；如果全部候选失败，命令以错误状态退出。

### 优化输出

```text
output/
├── optimization_history.csv       # 每一次目标函数评估
├── optimization_summary.json      # 最佳 R/C、指标和 SciPy 状态
├── optimization_progress.png      # 目标值与性能指标的优化过程曲线
└── runs/
    ├── evaluation_00001/
    │   ├── rc_lowpass.cir
    │   ├── ac_results.dat
    │   └── ngspice.log
    └── ...
```

CSV 包含候选 R/C、物理指标、优化器目标值、历史最佳值、状态、耗时、运行目录和失败原因。SQLite 优化实验还会保存最佳 R/C、最佳指标、目标误差、总评估数、成功/失败数、迭代数和总耗时。

## SQLite 实验管理

第四阶段使用 Python 标准库 `sqlite3` 保存实验。默认数据库为：

```text
experiments/circuitpilot.sqlite3
```

每条实验记录包含：

- 实验名称和电路类型；
- JSON 参数快照；
- 仿真耗时（秒）；
- JSON 数值性能指标；
- UTC 创建时间。

表结构带有 schema 版本和电路类型/时间索引，所有 SQL 写入均使用参数化查询。

### 自动保存仿真、扫描或优化

在原命令后增加 `--experiment-name` 即可保存成功结果，未提供该参数时原有行为不变：

```powershell
python main.py --config examples\lowpass.yaml `
  --experiment-name "RC low-pass baseline"

python main.py --sweep-config examples\sweep_lowpass.yaml `
  --experiment-name "10 kHz cutoff sweep"

python main.py --optimize-config examples\optimize_rc_cutoff.yaml `
  --experiment-name "10 kHz cutoff optimization"
```

可通过 `--experiment-database` 改变自动归档位置：

```console
python main.py --config examples/lowpass.yaml --experiment-name baseline --experiment-database output/history.sqlite3
```

扫描实验保存目标、参数空间、成功/失败数量、最佳截止频率和最佳相对误差；每个组合的完整明细仍保存在扫描 CSV 中。

优化实验保存连续边界、目标与求解器设置、最佳参数和指标；每一次目标函数调用仍保存在优化历史 CSV 中。

### Create experiment

可以直接用 JSON 参数和指标创建历史记录：

```powershell
python main.py experiment create `
  --name "manual baseline" `
  --circuit-type rc_lowpass `
  --parameters '{"R":1000,"C":1.59154943e-7}' `
  --simulation-time 0.05 `
  --metrics '{"cutoff_frequency_hz":997.7,"relative_error":0.0023}'
```

### List experiments

```console
python main.py experiment list
python main.py experiment list --circuit-type rc_lowpass --limit 10
```

### Show best result

默认寻找指标最小值：

```console
python main.py experiment best --metric relative_error
python main.py experiment best --metric cutoff_frequency_hz --maximize
```

### 历史实验比较

显式指定实验 ID 时，第一个 ID 是基线：

```console
python main.py experiment compare --metric cutoff_frequency_hz --ids 1 2 3
```

省略 ID 时按时间从最早实验开始比较，可按电路类型筛选：

```console
python main.py experiment compare --metric relative_error --circuit-type rc_lowpass
```

输出包含指标值、相对基线的绝对变化和相对变化。

## 单次参数化仿真

第二阶段配置仍然可用：

```console
python main.py --config examples/lowpass.yaml
python main.py --config examples/highpass.yaml
python main.py --config examples/voltage_divider.yaml
```

第一阶段无 YAML 的低通调用也继续有效：

```console
python -m circuitpilot --resistance 2200 --capacitance 47e-9 --start 10 --stop 1e6 --points 100
```

查看全部选项：

```console
python main.py --help
```

## 研究可复现产物

单次仿真、参数扫描和自动优化的每次调用都有唯一 `run_id`。省略 `--output-dir` 时，CircuitPilot 自动、原子地创建 `output/<run_id>`：

```powershell
python main.py --optimize-config examples\optimize_rc_cutoff.yaml
```

显式 `--output-dir` 表示该次实验的精确证据目录，只允许目录不存在或为空：

```powershell
python main.py --optimize-config examples\optimize_rc_cutoff.yaml `
  --output-dir output\runs\rc_cutoff_001 `
  --experiment-name "RC cutoff 20260801-001"
```

非空目录会被拒绝，防止静默覆盖。只有显式提供 `--resume` 才能进入已有 CircuitPilot run；目录必须包含有效 `run_context.json`，并且 YAML 必须与首次运行的 `input_config.yaml` 逐字节一致。恢复会保留同一 `run_id`、递增 `resume_count`，并重新执行所选工作流。

目录内的 `research_manifest.json` 保存完整配置、参数、指标、随机种子、run 身份、实际运行时间和全部证据文件 SHA-256。环境指纹包括 Git commit、Python/OS、NumPy、SciPy、PyYAML、CircuitPilot 版本、ngspice 版本字符串以及 ngspice 可执行文件 SHA-256。使用 YAML 时还会原样复制为 `input_config.yaml`；每个候选的 `.cir`、`ngspice.log` 和原始 `ac_results.dat` 都会保留。缺少任一类仿真证据时不会生成成功清单。

显式恢复示例：

```powershell
python main.py --optimize-config examples\optimize_rc_cutoff.yaml `
  --output-dir output\runs\rc_cutoff_001 --resume
```

`experiment create` 是保留的人工历史导入接口，其中的参数和指标由用户提供，不能作为“已由 ngspice 验证”的研究证据。研究结果应使用带 `--experiment-name` 的单次仿真、扫描或优化命令自动写入 SQLite，并以同目录的研究清单为依据。

可用以下脚本在临时全新虚拟环境中安装发行包、执行真实 ngspice 优化并核验 SQLite 与研究产物：

```powershell
python scripts\clean_environment_test.py `
  --ngspice tools\ngspice\bin\ngspice_con.exe
```

该脚本严格从 `requirements-research.lock` 安装锁定的直接与传递依赖，再以 `--no-deps --no-build-isolation` 安装 CircuitPilot，执行 `pip check` 和真实 ngspice 优化。首次执行需要能访问 Python 包索引；临时环境和运行目录在校验完成后自动清理。

## 测试

运行全部测试：

```console
python -m pytest
```

仅运行不依赖本地 ngspice 的测试：

```console
python -m pytest -m "not integration"
```

仅运行真实 ngspice 集成测试：

```console
python -m pytest -m integration
```

## Unified research experiments

Research Task 1 adds one optimizer-independent experiment path. The YAML form is:

```console
python -m circuitpilot.experiments.run --config research/configs/rc_baseline_seed0.yaml
```

The equivalent minimum CLI form is:

```console
python -m circuitpilot.experiments.run --circuit rc_lowpass --method random --seed 0 --budget 50
```

Every run receives a unique directory under `research_runs/` containing the resolved `experiment_config.yaml`, uniform `evaluations.csv` and SQLite records, per-candidate netlist/log/raw output, optimizer state, plots, summary, and the environment-fingerprinted `research_manifest.json`. Research comparison rules are defined in `research/EXPERIMENT_PROTOCOL.md`.

集成测试会自动检测本机 ngspice；未安装时明确显示为 `SKIPPED`。
