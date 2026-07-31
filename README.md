# CircuitPilot

CircuitPilot 是一个采用 `src/` 目录结构的参数化 ngspice 电路仿真与设计搜索平台。它可以从 YAML 读取单次仿真配置，也可以根据设计目标自动枚举元件参数、执行仿真、提取性能并排列最佳方案。

当前第三阶段支持：

- RC low-pass filter；
- RC high-pass filter；
- Voltage divider；
- YAML 配置读取、严格校验和不可变 Python 配置对象；
- ngspice AC 分析、频率/增益/相位解析和波特图；
- 低通下降穿越与高通上升穿越的 −3 dB 截止频率；
- R/C 参数范围和离散值的笛卡尔积扫描；
- 相对误差计算与 Top-N 方案排名；
- 全部实验结果 CSV 和“参数变化—性能”曲线；
- 单组失败隔离、ngspice 缺失预检和每组独立运行目录。

第一、二阶段的 API 和命令行方式继续保留。

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
│   └── sweep_lowpass.yaml
├── src/circuitpilot/
│   ├── analysis.py
│   ├── circuit_config.py
│   ├── cli.py
│   ├── exceptions.py
│   ├── experiment_manager.py       # SQLite 实验历史、最优结果与比较
│   ├── netlist.py                 # 第一阶段兼容 API
│   ├── netlist_generator.py
│   ├── parameter_sweep.py         # 执行、排名、CSV、性能图
│   ├── parser.py
│   ├── plotting.py
│   ├── simulator.py
│   └── sweep_config.py            # 扫描 YAML 与参数组合
└── tests/
```

## 环境与安装

要求 Python 3.10 或更高版本。运行依赖为 PyYAML 和 matplotlib，测试依赖为 pytest。

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

### 自动保存仿真或扫描

在原命令后增加 `--experiment-name` 即可保存成功结果，未提供该参数时原有行为不变：

```powershell
python main.py --config examples\lowpass.yaml `
  --experiment-name "RC low-pass baseline"

python main.py --sweep-config examples\sweep_lowpass.yaml `
  --experiment-name "10 kHz cutoff sweep"
```

可通过 `--experiment-database` 改变自动归档位置：

```console
python main.py --config examples/lowpass.yaml --experiment-name baseline --experiment-database output/history.sqlite3
```

扫描实验保存目标、参数空间、成功/失败数量、最佳截止频率和最佳相对误差；每个组合的完整明细仍保存在扫描 CSV 中。

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

集成测试会自动检测本机 ngspice；未安装时明确显示为 `SKIPPED`。
