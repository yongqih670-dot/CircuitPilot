"""Write the measured three-failure-corner v2 device-on audit."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_runs/task9_6_phase_b"
TRACKED = ROOT / "research/sky130/two_stage_ota/task9_6"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def numeric(value, scale=1.0, precision=5) -> str:
    return "UNKNOWN" if value is None else f"{value * scale:.{precision}g}"


def main() -> None:
    full = load(OUT / "baseline/evaluation.json")
    probes = load(OUT / "audit/device_probes.json")
    corners = {row["corner_id"]: row for row in full["raw_v2_result"]["corners"]}
    failed = ("ss__high_v_low_t", "fs__nominal", "fs__high_v_low_t")
    if set(probes) != set(failed) or any(probes[name]["process_status"] != "success" for name in failed):
        raise RuntimeError("three frozen failed-corner device probes are required")
    lines = ["# Task 9.6 device-on condition audit — real Benchmark v2",
             "", "The Task 9.5 best 12/15 design was rerun fresh: all 15 corners and",
             "45 OP/AC/transient analyses completed without analysis error.",
             "Exact robust violation is " + numeric(full["robust_feedback"]["exact_robust_violation"], precision=9)
             + "; 12/15 corners pass. The three preidentified failing corners were",
             "retained and independently probed for signed model Id, mirror node and",
             "external terminal coordinates (three additional charged processes).",
             "Raw evidence is in the two CRC-checked local audit archives and the",
             "machine-readable Full matrix. No v2 predicate was changed.", "",
             "## Stage and frozen hard-spec evidence", "",
             "| Corner | Gain dB | UGF MHz | PM ° | Power mW | Output V | +slew V/µs | −slew V/µs | Failed hard components |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for name in failed:
        row = corners[name]
        m = row["metrics"]
        failures = [key for key, value in row["constraint_components"].items() if value > 0]
        lines.append("| " + name + " | " + " | ".join((
            numeric(m["dc_gain_db"]), numeric(m["ugf_hz"], 1e-6),
            numeric(m["phase_margin_deg"]), numeric(m["dc_power_w"], 1e3),
            numeric(m["output_dc_voltage"]), numeric(m["positive_slew_v_per_s"], 1e-6),
            numeric(m["negative_slew_v_per_s"], 1e-6),
            ", ".join(failures))) + " |")
    lines.extend(["", "## Signed coordinates and independent predicates", "",
                  "The table keeps external ngspice-signed VGS/VDS and separately",
                  "type-oriented gate/drain voltages (NFET VGS/VDS; PFET VSG/VSD).",
                  "Internal model VTH and VDSAT are **not** substituted with external",
                  "terminal values. `on` means the frozen v2 internal VGS>VTH",
                  "and gm>0 predicate. `sat` is the separate internal VDSAT test.",
                  "All Id values below are raw internal model Id, in µA; the signed",
                  "supply-source current and stage voltages appear afterward.", "",
                  "| Corner | Role | Ext VGS / VDS V | Oriented gate / drain V | Model VTH / VDSAT V | On / headroom mV | Id µA | gm µS | gds µS | gm/abs(Id) V⁻¹ | on | sat |",
                  "| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |"])
    for name in failed:
        for role, d in probes[name]["devices"].items():
            model = d["model_internal_raw"]
            lines.append("| " + name + " | " + role + " | "
                + numeric(d["external_signed_vgs_v"]) + " / " + numeric(d["external_signed_vds_v"])
                + " | " + numeric(d["external_device_oriented_gate_v"]) + " / "
                + numeric(d["external_device_oriented_drain_v"])
                + " | " + numeric(model["vth"]) + " / " + numeric(model["vdsat"])
                + " | " + numeric(d["model_internal_on_margin_v"], 1e3)
                + " / " + numeric(d["model_internal_vdsat_headroom_v"], 1e3)
                + " | " + numeric(d["model_id_raw_a"], 1e6)
                + " | " + numeric(model["gm"], 1e6)
                + " | " + numeric(model["gds"], 1e6)
                + " | " + numeric(d["gm_over_id_inv_v"])
                + " | " + str(d["benchmark_on_condition_pass"])
                + " | " + str(d["model_saturation_condition_pass"]) + " |")
    lines.extend(["", "## Stage nodes and branch-current provenance", "",
                  "| Corner | Mirror V | Stage1 V | Tail V | Output V | Signed i(VDD) µA |",
                  "| --- | ---: | ---: | ---: | ---: | ---: |"])
    for name in failed:
        p = probes[name]
        n = p["node_voltages_v"]
        lines.append(f"| {name} | {numeric(n['mirror'])} | {numeric(n['stage1_out'])} | "
                     f"{numeric(n['tail'])} | {numeric(n['vout'])} | "
                     f"{numeric(p['signed_supply_current_a'], 1e6)} |")
    lines.extend(["", "Signed `i(VDD)` is the independently observed supply-source",
                  "current. The seven model Id values are internal transistor",
                  "quantities, not independently sensed external branch currents; no",
                  "unverified branch-current equality is asserted. For interpretation,",
                  "the measured tail Id is approximately the sum of the two input",
                  "model Id values, and second-stage / second-load magnitudes are",
                  "close, but subcircuit parasitics limit a direct KCL proof.", "",
                  "## Diagnosis and scope", "",
                  "- `ss__high_v_low_t`: first-stage load pair misses the v2 on predicate;",
                  "  all frozen performance metrics pass.",
                  "- `fs__nominal`: first-stage load pair misses the v2 on predicate;",
                  "  all frozen performance metrics pass.",
                  "- `fs__high_v_low_t`: input pair and first-stage load pair miss",
                  "  the v2 on predicate; negative slew also misses its hard minimum",
                  "  (measured 0.48875 versus required 0.5 V/µs).",
                  "", "Thus device-on semantics is not the sole blocker in the third corner.",
                  "Every listed off-predicate device still has finite, nonzero Id",
                  "and gm in this measured candidate; `benchmark_on_condition_fail`",
                  "does **not** mean zero current or a physically dead stage.",
                  "This identifies constraint violations and plausible interacting",
                  "bias/size/headroom mechanisms for one design, not a unique causal",
                  "explanation of the whole 12-dimensional feasible region. Five-corner",
                  "sensitivity and bounded search provide further, still finite-budget",
                  "evidence. The v2 benchmark and hard specs remain unchanged.", ""])
    (TRACKED / "DEVICE_ON_CONDITION_AUDIT.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote three-corner device-on audit")


if __name__ == "__main__":
    main()
