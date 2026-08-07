# Task 4 SKY130 Calibration Result

Calibration run ID: `cp-20260807T110401181924Z-9987aa0da32f`  
Pre-registration commit: `f555479590b713d77bba6ab430a2d935a77495c6`

The deterministic 256-point grid launched exactly 256 real ngspice processes.
All 256 completed successfully.  The measurement layer classified 192
bandwidths as exact and 64 as right-censored at the frozen 10 GHz stop
frequency.  No synthetic, default, or imputed bandwidth was introduced.

The observed physical ranges were:

- gain: -52.6023694 to 24.6031543 dB;
- exact bandwidth: 72.7508374 MHz to 9.38679613 GHz;
- DC supply power: 88.9033284 nW to 1.19932502 mW;
- output DC voltage: 0.00417820 to 1.79990106 V.

Applying the pre-registered threshold ladder and tie breaks selected:

- gain >= 14 dB;
- bandwidth >= 200 MHz;
- DC supply power <= 0.5 mW;
- 0.3 V <= output DC voltage <= 1.5 V;
- `operating_region_valid >= 1`.

Five of 256 grid points satisfy the complete frozen specification, a feasible
fraction of 1.953125%.  This is within the pre-registered 1%-3% target and is
closest to 2%; ties were resolved by higher gain, then higher bandwidth, then
lower power.  The formal optimizer budget therefore remains 50 evaluations.
