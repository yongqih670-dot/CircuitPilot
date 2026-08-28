# SKY130 Differential-Amplifier Benchmark Design

Status: topology and measurement design declared before Task 5 calibration.

## Topology

Task 5 uses a conventional five-transistor, single-ended differential
amplifier: an NMOS differential pair, a 1:1 PMOS current-mirror active load,
and a voltage-biased NMOS tail current source. This is the smallest standard
topology that introduces matched multi-device sizing, differential and
common-mode behavior, active loading, output bias, and tail-current trade-offs
without entering two-stage OTA design.

The differential input devices share one W/L by construction. The two PMOS
mirror devices share one W/L by construction. The tail device has its own W/L
and gate bias. Drain, gate, source, and bulk are explicit on every device.
NMOS bulks connect to ground and PMOS bulks connect to VDD.

## Testbenches

Two electrically isolated copies use the same candidate sizing in one netlist.
The differential copy uses VINP=0.5 at 0 degrees and VINN=0.5 at 180 degrees,
so the differential input magnitude is exactly 1 V. The common-mode copy uses
VINP=VINN=1 at 0 degrees. Ad and Acm are measured directly from their respective
outputs; CMRR is never formed by subtracting two noisy transient or
independently sized circuits.

One ngspice process performs one operating-point solve and one AC solve over
the two isolated copies. The primary budget unit is one candidate evaluation.
Each candidate records one ngspice process call, two physical analysis calls
(.op and .ac), and two logical AC testbenches.

## Technology

The benchmark reuses the content-locked Task 4 SKY130A/Open_PDKs 1.0.606 TT
installation and its model-tree and top-library hashes. Devices are the real
sky130_fd_pr__nfet_01v8 and sky130_fd_pr__pfet_01v8 primitives.

## Frozen Task 5 definition

Calibration selected Ad >= 15 dB, differential bandwidth >= 20 MHz, CMRR >=
35 dB, DC power <= 1 mW, output DC voltage in [0.25, 1.55] V, and valid
operation for all five critical devices. The formal budget is 100 candidate
evaluations. The independent Task 5 benchmark hash is
57d2183621ecf37e5ca22e012452c43fce6459be7d347a5cfc93d0b394c14378.
