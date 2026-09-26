# Task 9.6 local robust sensitivity — measured, five-corner partial

Measured 48 distinct in-bounds proposals × five frozen corners × 20
ngspice processes = 960 processes. All 240 corner diagnostics contain
OP/AC/transient plus an additional signed-current OP probe; no analysis
or probe error was recorded. The CSV contains 1,680 device-corner rows
with candidate value, five-corner baseline and signed difference for
all frozen performance metrics, model-on/VDSAT margins, Id, gm, gds,
floor-gated gm/Id, external signed/oriented terminals and stage nodes.
Every candidate is partial relative to the 15-corner objective; no
row here is a Full-PVT feasibility or exact-robust result.

| Variable | Best offset in normalized coordinate | Passed measured stages | Five-corner lower bound | Device-margin penalty (V) |
| --- | ---: | ---: | ---: | ---: |
| `tail_width_m` | +0.02 | 12/15 | 1 | 0.0593292 |
| `compensation_capacitance_f` | -0.04 | 12/15 | 1 | 0.0959493 |
| `input_pair_width_m` | +0.02 | 11/15 | 1.0143 | 0.105906 |
| `tail_length_m` | -0.02 | 11/15 | 1.01612 | 0.093261 |
| `second_load_length_m` | +0.02 | 11/15 | 1.01866 | 0.0959493 |
| `second_load_bias_v` | +0.02 | 11/15 | 1.02002 | 0.0959493 |
| `second_load_width_m` | -0.02 | 11/15 | 1.0201 | 0.0959493 |
| `input_pair_length_m` | -0.04 | 11/15 | 1.02076 | 0.100396 |
| `second_stage_width_m` | +0.02 | 11/15 | 1.02097 | 0.0959493 |
| `second_stage_length_m` | -0.02 | 11/15 | 1.02229 | 0.0959493 |
| `first_stage_load_length_m` | +0.02 | 11/15 | 1.02247 | 0.0892763 |
| `first_stage_load_width_m` | -0.01 | 11/15 | 1.02282 | 0.083893 |

Local proposal attention focuses on: `tail_width_m`, `compensation_capacitance_f`, `input_pair_width_m`, `tail_length_m`.
This is descriptive selection based on measured five-corner progress,
lower bound and device margin; all 12 Benchmark-v2 global bounds
remain available to DE and unchanged. The three failing-corner
baseline Id probes preceded sensitivity; the other two preselected
near-corner Id probes were completed afterward under the same
probe allocation. This ordering is disclosed because the frozen
protocol described baseline probes first. No corner was selected
post hoc and no result was remeasured to choose a favorable result.
Adaptive/local association is not a causal proof or a feasible-region
map. Baseline and candidate raw outputs are in CRC-checked local
archives; archive SHA-256s are in `archives/`.
