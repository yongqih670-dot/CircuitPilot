# Task 5 SKY130 Calibration Protocol

Status: declared before the first Task 5 calibration process.

- Design: 256-point, seven-dimensional, unscrambled Sobol sequence.
- Sequence seed metadata: 0; scramble is false.
- Candidate order: canonical Sobol order; no filtering or adaptive replacement.
- Circuit: frozen five-transistor differential amplifier.
- PDK: the Task 4 content-locked SKY130A/Open_PDKs 1.0.606 TT tree.
- Conditions: VDD 1.8 V, VCM 0.9 V, 27 C, CL 50 fF.
- AC window: 10 Hz-10 GHz, 30 points/decade.
- CMRR floor: common-mode gain at or below -120 dB yields a lower bound.
- Cost: 1 candidate, 1 ngspice process, 2 physical analyses, 2 logical AC testbenches.
- No Random, DE, TPE, BO, retry policy, candidate replacement, or LLM feedback.

Calibration publishes raw metrics and counts for exact/right-censored
bandwidth, exact/lower-bound CMRR, invalid responses, operating-region
validity, and process failures. The specification is selected only by
BENCHMARK_DIFFICULTY_PROTOCOL.md.

