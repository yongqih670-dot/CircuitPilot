# Task 9.5 Multiple Unity-Crossing Audit

## Fixed audit rule

The audit detects every sampled zero-dB crossing, both descending and
ascending, with the frozen logarithmic-frequency interpolation and unwrapped
phase.  For a valid low-frequency, above-unity non-inverting response, a
possible `phase_margin_semantics_v2` would use the minimum phase margin over
all **descending** unity crossings.  Ascending crossings are recorded but are
not substituted for the standard descending unity-gain stability margin.
This rule was coded and tested before scanning the responses; no historical
measurement or benchmark threshold was changed.

`scripts/task9_5_audit_crossings.py` scanned every local Task 7/8/9 primary AC
waveform still saved in the workspace, including Task 9 smoke shadow-Full
waveforms.  The result is `stability/all_ac_crossings.csv`: source path,
crossing count, every crossing frequency, direction, and phase margin, first
descending margin, critical descending margin, and parser status.  The
summary is `stability/crossing_summary.json`.

## Counts and classification impact

| Finding | Count |
|---|---:|
| Raw AC responses scanned | 28,247 |
| Historically valid, measured UGF responses | 17,344 |
| Valid measured responses with >1 total crossing | 0 |
| Raw responses with >1 total crossing | 882 |
| Candidate/run instances containing those responses | 440 |
| Responses where critical descending PM is worse than first | 0 |
| First PM >=35 deg but critical PM <35 deg | 0 |

Every one of the 882 multiple-crossing responses had an initial gain below
unity.  It contained an ascending crossing followed by a descending crossing;
the frozen UGF semantics classified it as `no_crossing` because a valid
low-frequency above-unity response was absent.  This explains the 882 raw
descending-count mismatches against the historical *valid UGF* crossing count:
the historical count is intentionally zero for these invalid responses.  It
does not indicate a missed second descending crossing in a valid response.
The 440 count is based on run/candidate identifiers and can include repeated
parameter vectors in paired policies or separate corners.

For Task 9 specifically, the formal equal-candidate, formal equal-time, and
smoke raw files contributed respectively 357, 189, and 103 of the 882
multiple-crossing response instances.  None was a historically valid measured
UGF.  Thus no saved Task 7/8 nominal feasible classification and no Task 9
PVT feasible classification changes under the preregistered critical
descending-margin rule.  Historical first-crossing PM semantics can remain
for the old benchmark on this evidence; a separate v2 hash is unnecessary
*because of PM alone*.

## Coverage limit

Task 9's nominal-gap 27 x 15 and Sobol64 x 15 Full-PVT matrices retain parsed
`ugf_crossing_count` but no raw AC response waveforms.  Their saved counts are
all 0 or 1 descending crossing, so using the minimum of descending margins
cannot change a recorded measured PM in those matrices.  Additional ascending
crossings cannot be independently enumerated there.  The audit therefore does
not claim direct waveform coverage of those 1,365 preformal corners.

This is a finite frequency-grid audit.  It does not prove continuous-time
closed-loop stability between samples or outside the frozen 10 Hz--10 GHz
window.  It does directly answer the specified first-versus-critical
crossing question for the saved responses.
