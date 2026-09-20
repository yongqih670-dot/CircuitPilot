# Task 9 Static Corner Order

The pre-registered lexicographic rule was applied once to the completed Sobol64
Full-PVT matrix under selected specification row 0.  The frozen formal order is:

```text
sf__nominal, ss__low_v_high_t, tt__low_v_high_t, ff__low_v_high_t, ss__nominal, tt__nominal, ff__nominal, ss__high_v_low_t, fs__low_v_high_t, tt__high_v_low_t, fs__nominal, fs__high_v_low_t, sf__low_v_high_t, sf__high_v_low_t, ff__high_v_low_t
```

Corner-order SHA-256: `e07c17b9041c271e15d49d3362253db3a21fcd6eede169158dd18c7bb975fc56`.

| Rank | Corner | Rejection fraction | Mean normalized violation | Mean complete-corner ngspice s |
|---:|---|---:|---:|---:|
| 1 | `sf__nominal` | 100.0% | 6.132558 | 2.535 |
| 2 | `ss__low_v_high_t` | 100.0% | 5.696104 | 2.489 |
| 3 | `tt__low_v_high_t` | 100.0% | 5.610770 | 2.491 |
| 4 | `ff__low_v_high_t` | 100.0% | 5.568247 | 2.506 |
| 5 | `ss__nominal` | 100.0% | 5.444621 | 2.504 |
| 6 | `tt__nominal` | 100.0% | 5.305125 | 2.497 |
| 7 | `ff__nominal` | 100.0% | 5.285220 | 2.504 |
| 8 | `ss__high_v_low_t` | 100.0% | 5.037487 | 2.474 |
| 9 | `fs__low_v_high_t` | 100.0% | 4.856736 | 2.541 |
| 10 | `tt__high_v_low_t` | 100.0% | 4.827953 | 2.509 |
| 11 | `fs__nominal` | 100.0% | 4.818169 | 2.510 |
| 12 | `fs__high_v_low_t` | 100.0% | 4.707384 | 2.523 |
| 13 | `sf__low_v_high_t` | 98.4% | 6.594386 | 2.492 |
| 14 | `sf__high_v_low_t` | 98.4% | 5.358299 | 2.520 |
| 15 | `ff__high_v_low_t` | 98.4% | 4.785104 | 2.494 |

The order is static for every later candidate and is not an adaptive corner
predictor.  Exact unrounded sort inputs are stored in
`calibration/static_corner_order.json`; component failures, runtime fields, and
nominal-first first-failure probabilities are retained in the companion CSVs.
