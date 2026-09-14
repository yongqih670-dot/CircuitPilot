# SKY130 Common-Source Search-Space Rationale

Status: frozen before calibration under protocol `task4_sky130_difficulty_v1`.

The Task 4 device is the real four-terminal `sky130_fd_pr__nfet_01v8` from the
content-locked Open_PDKs SKY130A installation.  Task 3's reference-model ranges
are not reused.

| Parameter | Search range | Rationale |
| --- | ---: | --- |
| `width_m` | 0.42–7.0 µm, log | Uses the characterized standard-device width span represented by the official 63-bin model while excluding the separate sub-0.42 µm special-cell regime. |
| `length_m` | 0.15–1.0 µm | Covers minimum length and several characterized longer-channel bins without extrapolating to Task 3's unrelated 2 µm upper bound. |
| `drain_resistance_ohm` | 2–100 kΩ, log | Provides meaningful gain/current trade-offs at 1.8 V while avoiding near-short loads and impractically weak bias currents. |
| `input_bias_v` | 0.55–1.05 V | Brackets threshold and useful inversion/bias points while remaining inside the 1.8 V model domain. |

Fixed conditions are VDD = 1.8 V, CL = 20 fF, temperature = 27 °C, and bulk
explicitly connected to ground.  Width and length are stored in SI units by
CircuitPilot and converted to the Open_PDKs subcircuit's micrometre parameters
in the generated netlist.

The fixed AC window is 10 Hz–10 GHz at 30 points/decade for every candidate.
No optimizer or candidate receives an adaptive sweep.

