"""Derive auditable five-corner sensitivity tables from Phase-B raw results."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from circuitpilot.sky130_two_stage_ota import DEVICE_ROLES
from circuitpilot.task9_protocol import CONSTRAINT_NAMES, corner_constraint_components


OUT = ROOT / "research_runs/task9_6_phase_b"
TRACKED = ROOT / "research/sky130/two_stage_ota/task9_6"
PERFORMANCE = tuple(name for name in CONSTRAINT_NAMES if name != "operating_region")
METRICS = ("dc_gain_db", "ugf_hz", "phase_margin_deg", "dc_power_w",
           "output_dc_voltage", "positive_slew_v_per_s", "negative_slew_v_per_s")
DEVICE = ("model_internal_on_margin_v", "model_internal_vdsat_headroom_v",
          "model_id_raw_a", "gm_over_id_inv_v", "external_signed_vgs_v",
          "external_signed_vds_v", "external_device_oriented_gate_v",
          "external_device_oriented_drain_v")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def combined_corner(row: dict) -> tuple[dict, dict, dict]:
    op = row["v2_op"]
    metrics = dict(op["metrics"])
    statuses = dict(op["statuses"])
    for stage in ("ac", "transient"):
        metrics.update(row[stage]["metrics"])
        statuses.update(row[stage]["statuses"])
    components = corner_constraint_components(metrics, statuses)
    return metrics, statuses, components


def main() -> None:
    frozen = load(TRACKED / "sensitivity_candidates.json")
    corners = frozen["corner_ids"]
    baseline_full = load(OUT / "baseline/evaluation.json")["raw_v2_result"]
    baseline_by_id = {row["corner_id"]: row for row in baseline_full["corners"]}
    probes = load(OUT / "audit/device_probes.json")
    probes.update(load(OUT / "audit_extra/device_probes.json"))
    if set(probes) != set(corners) or any(row["process_status"] != "success" for row in probes.values()):
        raise RuntimeError("all five baseline diagnostic Id probes are required")
    baseline_devices = {corner: probes[corner]["devices"] for corner in corners}
    records = []
    candidates = []
    for index, proposal in enumerate(frozen["candidates"]):
        result = load(OUT / "sensitivity" / f"candidate_{index:02d}" / "diagnostic.json")
        if result["robust_evaluation_status"] != "partial" or result["exact_robust_violation"] is not None:
            raise RuntimeError("five-corner sensitivity cannot be exact Full-PVT")
        lower = {name: [] for name in CONSTRAINT_NAMES}
        passed_stages, passed_corners, invalid = 0, 0, 0
        device_penalty = 0.0
        for row in result["corners"]:
            corner_id = row["corner_id"]
            if (row["v2_op"]["analysis_errors"].get("op")
                    or row["ac"]["error"] or row["transient"]["error"]
                    or row["diagnostic_op"].get("process_status") != "success"):
                invalid += 1
                continue
            metrics, statuses, components = combined_corner(row)
            for name, value in components.items():
                lower[name].append(value)
            passed_stages += sum(int(all(components[name] == 0 for name in names))
                                 for names in (("operating_region", "power_max", "output_low", "output_high"),
                                               ("gain_min", "ugf_min", "phase_margin_min"),
                                               ("positive_slew_min", "negative_slew_min")))
            passed_corners += int(all(value == 0 for value in components.values()))
            devices = row["diagnostic_op"]["devices"]
            device_penalty += sum(max(0.0, -device["model_internal_on_margin_v"])
                                  + max(0.0, -device["model_internal_vdsat_headroom_v"])
                                  for device in devices.values())
            for role in DEVICE_ROLES:
                device = devices[role]
                base_device = baseline_devices[corner_id][role]
                base_metrics = baseline_by_id[corner_id]["metrics"]
                record = {
                    "candidate_index": index,
                    "variable": proposal["parameter"],
                    "normalized_offset": proposal["normalized_offset"],
                    "boundary_limited": proposal["boundary_limited"],
                    "corner_id": corner_id, "device_role": role,
                    "benchmark_on_condition_pass": device["benchmark_on_condition_pass"],
                    "model_saturation_condition_pass": device["model_saturation_condition_pass"],
                    "functional_stage_metrics_pass": all(components[name] == 0 for name in PERFORMANCE),
                }
                for name in DEVICE:
                    value, base = device[name], base_device[name]
                    record[name] = value
                    record["baseline_" + name] = base
                    record["delta_" + name] = None if value is None or base is None else value - base
                for name in ("gm", "gds"):
                    value = device["model_internal_raw"][name]
                    base = base_device["model_internal_raw"][name]
                    record[name] = value
                    record["baseline_" + name] = base
                    record["delta_" + name] = value - base
                for name in METRICS:
                    value, base = metrics.get(name), base_metrics.get(name)
                    record[name] = value
                    record["baseline_" + name] = base
                    record["delta_" + name] = None if value is None or base is None else value - base
                for node, value in row["diagnostic_op"]["node_voltages_v"].items():
                    record["node_" + node + "_v"] = value
                    record["delta_node_" + node + "_v"] = value - probes[corner_id]["node_voltages_v"][node]
                record["signed_supply_current_a"] = row["diagnostic_op"]["signed_supply_current_a"]
                record["baseline_signed_supply_current_a"] = probes[corner_id]["signed_supply_current_a"]
                records.append(record)
        measured_lower = sum(max(values) for values in lower.values() if values)
        score = (-passed_stages, -passed_corners, measured_lower, device_penalty,
                 proposal["parameter_vector_sha256"])
        candidates.append({"candidate_index": index, "variable": proposal["parameter"],
                           "normalized_offset": proposal["normalized_offset"],
                           "passed_measured_stages": passed_stages,
                           "passed_complete_measured_corners": passed_corners,
                           "five_corner_violation_lower_bound": measured_lower,
                           "device_margin_penalty_v": device_penalty,
                           "invalid_corner_count": invalid,
                           "diagnostic_order": score})
    if len(records) != 48 * 5 * 7 or any(row["invalid_corner_count"] for row in candidates):
        raise RuntimeError("sensitivity measurements incomplete; do not rank")
    per_variable = {}
    for row in candidates:
        name = row["variable"]
        if name not in per_variable or tuple(row["diagnostic_order"]) < tuple(per_variable[name]["diagnostic_order"]):
            per_variable[name] = row
    focus = [name for name, row in sorted(per_variable.items(),
             key=lambda pair: (tuple(pair[1]["diagnostic_order"]), pair[0]))[:4]]
    summary = {"schema_version": "task9_6_local_sensitivity_analysis_v1",
               "benchmark_v2_hash": frozen["benchmark_v2_hash"],
               "five_corner_partial_only": True,
               "corner_ids": corners, "candidate_count": len(candidates),
               "device_corner_rows": len(records),
               "candidates": candidates, "best_by_variable": per_variable,
               "diagnostic_attention_subset": focus,
               "best_five_corner_candidate_index": min(candidates,
                    key=lambda row: tuple(row["diagnostic_order"]))["candidate_index"]}
    destination = TRACKED / "sensitivity_analysis.json"
    destination.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    columns = list(records[0])
    for row in records[1:]:
        columns.extend(name for name in row if name not in columns)
    with (TRACKED / "LOCAL_ROBUST_SENSITIVITY.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(records)
    lines = ["# Task 9.6 local robust sensitivity — measured, five-corner partial",
             "", f"Measured 48 distinct in-bounds proposals × five frozen corners × 20",
             "ngspice processes = 960 processes. All 240 corner diagnostics contain",
             "OP/AC/transient plus an additional signed-current OP probe; no analysis",
             "or probe error was recorded. The CSV contains 1,680 device-corner rows",
             "with candidate value, five-corner baseline and signed difference for",
             "all frozen performance metrics, model-on/VDSAT margins, Id, gm, gds,",
             "floor-gated gm/Id, external signed/oriented terminals and stage nodes.",
             "Every candidate is partial relative to the 15-corner objective; no",
             "row here is a Full-PVT feasibility or exact-robust result.", "",
             "| Variable | Best offset in normalized coordinate | Passed measured stages | Five-corner lower bound | Device-margin penalty (V) |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for name, row in sorted(per_variable.items(), key=lambda pair: tuple(pair[1]["diagnostic_order"])):
        lines.append(f"| `{name}` | {row['normalized_offset']:+.2f} | {row['passed_measured_stages']}/15 | "
                     f"{row['five_corner_violation_lower_bound']:.6g} | {row['device_margin_penalty_v']:.6g} |")
    lines.extend(["", "Local proposal attention focuses on: " + ", ".join(f"`{name}`" for name in focus) + ".",
                  "This is descriptive selection based on measured five-corner progress,",
                  "lower bound and device margin; all 12 Benchmark-v2 global bounds",
                  "remain available to DE and unchanged. The three failing-corner",
                  "baseline Id probes preceded sensitivity; the other two preselected",
                  "near-corner Id probes were completed afterward under the same",
                  "probe allocation. This ordering is disclosed because the frozen",
                  "protocol described baseline probes first. No corner was selected",
                  "post hoc and no result was remeasured to choose a favorable result.",
                  "Adaptive/local association is not a causal proof or a feasible-region",
                  "map. Baseline and candidate raw outputs are in CRC-checked local",
                  "archives; archive SHA-256s are in `archives/`.", ""])
    (TRACKED / "LOCAL_ROBUST_SENSITIVITY_REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Analyzed {len(candidates)} local candidates; focus={focus}")


if __name__ == "__main__":
    main()
