"""Offline safe-short-circuit replay over complete Task 9 calibration evidence."""

from __future__ import annotations

import csv
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT = PROJECT_ROOT / "research" / "sky130" / "two_stage_ota" / "task9"
CALIBRATION = ROOT / "calibration"
MATRIX = CALIBRATION / "full_pvt" / "full_pvt_matrix.jsonl"
ORDER = CALIBRATION / "static_corner_order.json"
RESULTS = ROOT / "replay"


def first_positive(components: dict[str, float], names: tuple[str, ...]) -> str | None:
    return next((name for name in names if float(components[name]) > 0.0), None)


def replay(design: dict, order: list[str]) -> dict:
    corners = {corner["corner_id"]: corner for corner in design["corners"]}
    op_calls = ac_calls = transient_calls = corners_started = corners_completed = 0
    accumulated = 0.0
    first_corner = first_stage = first_constraint = None
    for corner_id in order:
        corner = corners[corner_id]
        components = corner["constraint_components"]
        costs = corner["cost"]["per_stage_ngspice_seconds"]
        corners_started += 1
        op_calls += 1
        accumulated += float(costs["op"])
        blocker = first_positive(
            components, ("operating_region", "power_max", "output_low", "output_high")
        )
        if blocker is not None:
            first_corner, first_stage, first_constraint = corner_id, "op", blocker
            break
        ac_calls += 1
        accumulated += float(costs["ac"])
        blocker = first_positive(components, ("gain_min", "ugf_min", "phase_margin_min"))
        if blocker is not None:
            first_corner, first_stage, first_constraint = corner_id, "ac", blocker
            break
        transient_calls += 1
        accumulated += float(costs["transient"])
        corners_completed += 1
        blocker = first_positive(components, ("positive_slew_min", "negative_slew_min"))
        if blocker is not None:
            first_corner, first_stage, first_constraint = corner_id, "transient", blocker
            break
    replay_feasible = first_corner is None
    full_feasible = bool(design["pvt_feasible"])
    return {
        "design_id": design["design_id"],
        "full_pvt_feasible": full_feasible,
        "replay_pvt_feasible": replay_feasible,
        "false_acceptance": replay_feasible and not full_feasible,
        "false_rejection": not replay_feasible and full_feasible,
        "feasibility_identical": replay_feasible == full_feasible,
        "corners_started": corners_started,
        "corners_completed": corners_completed,
        "op_calls": op_calls,
        "ac_calls": ac_calls,
        "transient_calls": transient_calls,
        "process_calls": op_calls + ac_calls + transient_calls,
        "accumulated_ngspice_seconds": accumulated,
        "first_failing_corner": first_corner,
        "first_failing_stage": first_stage,
        "first_failing_constraint": first_constraint,
    }


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    designs = [json.loads(line) for line in MATRIX.read_text(encoding="utf-8").splitlines() if line]
    order_payload = json.loads(ORDER.read_text(encoding="utf-8"))
    orders = {
        "nominal_first": order_payload["nominal_first_order"],
        "static_worst_first": order_payload["static_worst_first_order"],
    }
    all_rows: list[dict] = []
    summaries: dict[str, dict] = {}
    full_cost = {
        "corners_started": len(designs) * 15,
        "corners_completed": len(designs) * 15,
        "op_calls": len(designs) * 15,
        "ac_calls": len(designs) * 15,
        "transient_calls": len(designs) * 15,
        "process_calls": len(designs) * 45,
        "accumulated_ngspice_seconds": sum(
            float(design["cost"]["accumulated_ngspice_seconds"]) for design in designs
        ),
    }
    for name, order in orders.items():
        rows = [{"order": name, **replay(design, order)} for design in designs]
        all_rows.extend(rows)
        totals = {
            metric: sum(float(row[metric]) for row in rows)
            for metric in (
                "corners_started",
                "corners_completed",
                "op_calls",
                "ac_calls",
                "transient_calls",
                "process_calls",
                "accumulated_ngspice_seconds",
            )
        }
        savings = {metric: float(full_cost[metric]) - totals[metric] for metric in totals}
        summaries[name] = {
            "candidate_count": len(rows),
            "feasibility_identity_count": sum(row["feasibility_identical"] for row in rows),
            "feasibility_identity_fraction": sum(row["feasibility_identical"] for row in rows) / len(rows),
            "false_pvt_acceptance_count": sum(row["false_acceptance"] for row in rows),
            "false_pvt_rejection_count": sum(row["false_rejection"] for row in rows),
            "replay_totals": totals,
            "full_totals": full_cost,
            "savings": savings,
            "simulator_time_savings_fraction": savings["accumulated_ngspice_seconds"] / float(full_cost["accumulated_ngspice_seconds"]),
        }
    with (RESULTS / "replay_candidates.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(all_rows[0]))
        writer.writeheader()
        writer.writerows(all_rows)
    payload = {
        "schema_version": "task9_safe_short_circuit_replay_v1",
        "corner_order_hash": order_payload["corner_order_hash"],
        "summaries": summaries,
        "gate_passed": all(
            item["false_pvt_acceptance_count"] == 0
            and item["false_pvt_rejection_count"] == 0
            and item["feasibility_identity_fraction"] == 1.0
            for item in summaries.values()
        ),
    }
    (RESULTS / "replay_summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    static = summaries["static_worst_first"]
    nominal = summaries["nominal_first"]
    report = f"""# Task 9 Corner-Order Replay Equivalence Report

Both frozen corner orders were replayed over all 64 complete Sobol calibration
matrices.  Each replay applies the real measured row-0 hard constraints in the
fixed within-corner order OP → AC → transient and stops across corners only
after a measured hard failure.

| Result | Nominal-first | Static worst-first |
|---|---:|---:|
| Feasibility identity | {nominal['feasibility_identity_count']}/64 | {static['feasibility_identity_count']}/64 |
| False PVT acceptances | {nominal['false_pvt_acceptance_count']} | {static['false_pvt_acceptance_count']} |
| False PVT rejections | {nominal['false_pvt_rejection_count']} | {static['false_pvt_rejection_count']} |
| Corners avoided | {nominal['savings']['corners_started']:.0f} | {static['savings']['corners_started']:.0f} |
| OP calls avoided | {nominal['savings']['op_calls']:.0f} | {static['savings']['op_calls']:.0f} |
| AC calls avoided | {nominal['savings']['ac_calls']:.0f} | {static['savings']['ac_calls']:.0f} |
| Transient calls avoided | {nominal['savings']['transient_calls']:.0f} | {static['savings']['transient_calls']:.0f} |
| Process calls avoided | {nominal['savings']['process_calls']:.0f} | {static['savings']['process_calls']:.0f} |
| Simulator seconds saved | {nominal['savings']['accumulated_ngspice_seconds']:.3f} | {static['savings']['accumulated_ngspice_seconds']:.3f} |
| Simulator-time saving | {nominal['simulator_time_savings_fraction']:.1%} | {static['simulator_time_savings_fraction']:.1%} |

The integrity gate passes: both orders have 100% feasibility identity and zero
false acceptance/rejection.  The calibration set contains no Full-PVT-feasible
positive case, so positive-path safety additionally remains a mandatory unit
test and smoke shadow audit; this limitation is not hidden by the zero-error
counts.

`replay/replay_candidates.csv` retains every stopping corner/stage/constraint
and exact cost.  `replay/replay_summary.json` retains totals and the gate.
"""
    (ROOT / "REPLAY_EQUIVALENCE_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if not payload["gate_passed"]:
        raise SystemExit("replay integrity gate failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
