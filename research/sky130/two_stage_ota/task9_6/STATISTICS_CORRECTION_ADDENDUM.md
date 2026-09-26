# Task 6 equal-AC RMST wording addendum

This clarifies the Task 9.5 statistical explanation without changing any
historical Task 6 or Task 9.5 data, RMST values, benchmark hashes, or formal
conclusions. The corrected numerical table remains
`task9_5/statistics/corrected_rmst.csv`.

Two different issues must not be conflated:

1. **Genuine unsupported positive-tail extrapolation.** In the Task 6
   equal-AC experiment, BO Full's candidate-count observations end at 100
   candidates, but the historical RMST integrated to 300. Its historical
   169.000 therefore includes an unobserved *positive* survival tail. The
   common supported candidate-count horizon is 100 (BO Screened was observed
   to 300), giving corrected Full 69.000 and Screened 83.400. It is correct
   to call the Full 100→300 extension unsupported.
2. **Conservative common truncation for comparison.** On the pooled
   expensive-AC axis, Full has event/censoring observation support through
   200 AC calls, while Screened's maximum observed time is 92. The
   comparison uses the predeclared rule
   `tau_common = min(max_observed_Full, max_observed_Screened) = 92`.
   Full's corrected pooled RMST is 76.100 at 92 rather than its historical
   119.850 at 200; Screened is 34.742 at both horizons because its KM
   survival had already reached zero. The Full 92→200 portion is **not**
   unsupported for Full; it is excluded to put both groups on the same
   observed comparison horizon. It is incorrect to say Full lacked 200-AC
   observation support.

The same distinction applies by method: BO's AC comparison horizon is 84,
DE's 92, Random's 70, and TPE's 80, each the minimum of that pair's group
maxima. A KM curve that reaches survival zero after observed events can have
a mathematically zero tail past the last at-risk participant; integrating
that zero tail is not the same as extending an unobserved *positive*
survival tail. Nevertheless, the audit adopts the conservative common
observed horizon for all comparative RMST values and the estimator refuses
requests beyond a group's observed support. The supported-horizon rule is
about fair paired/group comparison, not a claim that every old one-group
Full estimate to 200 was unsupported.

Task 6 H2 remains supported: formal pooled equal-AC success was 37/40 for
Screened versus 28/40 for Full, with comparable corrected AC RMST 34.742
versus 76.100 at 92 AC calls. The old 119.850 must not be cited as the
equal-horizon Full comparator. No historical report is rewritten.
