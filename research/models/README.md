# Transistor model provenance

`ngspice_bsim3_nmos.lib` is an exact copy of
`examples/mos/modelcard.nmos` from the official ngspice 46 Windows binary
distribution installed under `tools/ngspice` for CircuitPilot. It is a BSIM3
reference model named `N1`; it is **not** a SKY130 PDK model and must never be
reported as one. The exact file SHA-256 is recorded by every transistor-level
run.

The Common-Source benchmark consumes model paths through YAML or an environment
variable. A later SKY130 installation can therefore replace this library only
by creating and freezing a new benchmark hash.
