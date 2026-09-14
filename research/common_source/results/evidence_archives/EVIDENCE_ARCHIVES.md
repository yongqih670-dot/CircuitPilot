# Research evidence archives

These ZIP files preserve the complete per-evaluation evidence for the authoritative
Task 2 and Task 3 runs. They are byte-for-byte archives of the corresponding local
`research_runs/` run directories; no failed evaluations or raw ngspice artifacts
were removed.

| Scope | Run ID | Archive bytes | ZIP entries | SHA-256 |
| --- | --- | ---: | ---: | --- |
| Task 2 locked RC baseline | `cp-20260807T072934991033Z-24df007f46f8` | 2,739,038 | 849 | `737f0b1c039536b6ff1b79a038252b3f1dedd419e734881e77d9b69b4e5c629c` |
| Task 3 common-source calibration | `cp-20260807T081320668324Z-c257acc459b6` | 443,924 | 504 | `d712131b3f34ea715f13f6b7e6a26c29d0798b390b600050e939554fc77a5f8a` |
| Task 3 common-source smoke suite | `cp-20260807T082352367430Z-3f967f1d65bc` | 3,400,126 | 2,014 | `a3fb72127356a97baabb40e87f65051c6732fa41d0272ad191d7afe12f6bfe2c` |
| Task 3 locked common-source baseline | `cp-20260807T083800448980Z-5be94980f0c1` | 18,069,198 | 12,840 | `4f2aa3af6246791342cc6fac810453bea7ed1ecbfc56d3214d8ee10c610ab756` |

Each archive contains the run-level configuration and manifest plus the complete
evaluation tree. Depending on the experiment, candidate directories include the
generated netlist, ngspice log, parsed/raw AC output, DC operating-point output,
MOS operating-point output, parameters, metrics, status, and timing records.

## Verification

On PowerShell, verify an archive before using it:

```powershell
Get-FileHash -Algorithm SHA256 <archive.zip>
```

Extract into a new empty directory. The archive includes its run directory as the
top-level folder, so it does not overwrite the existing `research_runs/` tree by
default.
