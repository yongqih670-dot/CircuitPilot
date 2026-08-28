# Task 5 SKY130 Calibration Result

Calibration run ID: cp-20260828T080034521618Z-7c37868f2b79

Pre-registration commit: ca7e7fb634b27458195b18745e66db7be4ad7bb9

The first 256 points of the frozen unscrambled seven-dimensional Sobol sequence
launched exactly 256 real ngspice processes. All 256 processes and measurements
completed. The physical cost was 256 candidate evaluations, 256 ngspice process
calls, and 512 analysis calls. There were no simulator failures, analysis
errors, or invalid differential/common-mode responses.

All 256 differential bandwidths were exact; none was right-censored. All 256
CMRR values were exact; none used the -120 dB common-mode-floor lower-bound
semantics. Forty candidates placed every critical transistor in the explicitly
defined operating region.

Observed ranges and medians were:

| Metric | Minimum | Median | Maximum |
|---|---:|---:|---:|
| Differential gain | -12.840458 dB | 33.178601 dB | 41.9083505 dB |
| Exact bandwidth | 39.1289 kHz | 4.20508 MHz | 698.600 MHz |
| Exact CMRR | -0.925902 dB | 55.9683463 dB | 80.868947 dB |
| DC supply power | 39.6124 nW | 16.3949 uW | 231.290 uW |
| Output DC voltage | 0.0990910 V | 0.757721 V | 1.401787 V |
| Tail current | 22.0029 nA | 9.10829 uA | 128.494 uA |
| Candidate runtime | 0.625 s | 0.734 s | 0.844 s |

The pre-registered ladder selected row 1:

- differential gain >= 15 dB;
- bandwidth >= 20 MHz;
- CMRR >= 35 dB;
- DC supply power <= 1 mW;
- output DC voltage in [0.25, 1.55] V;
- all critical transistors satisfy operating_region_valid.

Two of 256 candidates satisfy the complete specification, a feasible fraction
of 0.78125%. This is inside the pre-registered 0.5%-3.0% target band. All later
ladder rows had zero feasible candidates. The median runtime is below the
pre-registered 1.5-second cutoff, so the formal optimizer budget is frozen at
100 candidate evaluations.

The Sobol candidate-design SHA-256 is
1345d5b3b4a318cbade769c1d63ec0e4b512d2817f20067b6462724597d45f25.
The frozen Task 5 benchmark hash is
57d2183621ecf37e5ca22e012452c43fce6459be7d347a5cfc93d0b394c14378.

