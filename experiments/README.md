# CircuitPilot experiment results

This directory contains the SQLite experiment history and selected reproducible
artifacts generated with the project-local ngspice 46 installation on
2026-07-31.

## SQLite history

Database: `circuitpilot.sqlite3`

| ID | Experiment | Circuit | Simulation time | Key result |
|---:|---|---|---:|---|
| 1 | RC low-pass 1 kHz baseline | `rc_lowpass` | 0.031 s | cutoff 997.705 Hz |
| 2 | RC low-pass 10 kHz parameter sweep | `rc_lowpass` | 12.375 s | 300/300 successful |

The database can be inspected through the public CLI:

```console
python main.py experiment list
python main.py experiment best --metric best_relative_error
```

## 1 kHz baseline

Directory: `artifacts/rc_lowpass_baseline/`

- default R = 1 kΩ and C ≈ 159.154943 nF;
- 501 AC samples;
- simulated −3 dB cutoff: 997.705 Hz;
- includes the netlist, ngspice data/log, and Bode plot.

## 10 kHz parameter sweep

Directory: `artifacts/rc_lowpass_10khz_sweep/`

- R = 100 Ω through 10 kΩ in 100 Ω steps;
- C ∈ {1 nF, 10 nF, 100 nF};
- 300 parameter combinations, all successful;
- full CSV and parameter-performance plot are included;
- the complete rank-1 ngspice run is preserved under `best_run/`.

Top result:

| Rank | R | C | Simulated cutoff | Relative error |
|---:|---:|---:|---:|---:|
| 1 | 1600 Ω | 10 nF | 9922.9597 Hz | 0.7704% |

The source sweep configuration is `../examples/sweep_lowpass.yaml`.
